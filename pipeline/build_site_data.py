"""Build the static site's data files for one state from:
  - the BU CSV (bweb_<turno>_<UF>_*.csv) published by the TSE,
  - the per-urna parquet files produced by run_full.py (parsed urna logs),
  - municipal boundaries (geodata-br, derived from IBGE).

Nothing is estimated: every count is a direct aggregation of the published files. Each urna's log is
checked against its BU (voters and "não habilitados por biometria"); mismatches are reported.

usage: python build_site_data.py --uf BA --bweb <csv> --logs <dir> --geo-mun <geojson> --states-geo <geojson> --out site/
"""
import argparse, glob, json, os, re, unicodedata, datetime as dt
import numpy as np, pandas as pd, pyarrow.parquet as pq

STATES = [  # code, uf, name, region
    ('11', 'RO', 'Rondônia', 'N'), ('12', 'AC', 'Acre', 'N'), ('13', 'AM', 'Amazonas', 'N'), ('14', 'RR', 'Roraima', 'N'),
    ('15', 'PA', 'Pará', 'N'), ('16', 'AP', 'Amapá', 'N'), ('17', 'TO', 'Tocantins', 'N'),
    ('21', 'MA', 'Maranhão', 'NE'), ('22', 'PI', 'Piauí', 'NE'), ('23', 'CE', 'Ceará', 'NE'), ('24', 'RN', 'Rio Grande do Norte', 'NE'),
    ('25', 'PB', 'Paraíba', 'NE'), ('26', 'PE', 'Pernambuco', 'NE'), ('27', 'AL', 'Alagoas', 'NE'), ('28', 'SE', 'Sergipe', 'NE'), ('29', 'BA', 'Bahia', 'NE'),
    ('31', 'MG', 'Minas Gerais', 'SE'), ('32', 'ES', 'Espírito Santo', 'SE'), ('33', 'RJ', 'Rio de Janeiro', 'SE'), ('35', 'SP', 'São Paulo', 'SE'),
    ('41', 'PR', 'Paraná', 'S'), ('42', 'SC', 'Santa Catarina', 'S'), ('43', 'RS', 'Rio Grande do Sul', 'S'),
    ('50', 'MS', 'Mato Grosso do Sul', 'CO'), ('51', 'MT', 'Mato Grosso', 'CO'), ('52', 'GO', 'Goiás', 'CO'), ('53', 'DF', 'Distrito Federal', 'CO'),
]
REGIONS = [('N', 'Norte'), ('NE', 'Nordeste'), ('CO', 'Centro-Oeste'), ('SE', 'Sudeste'), ('S', 'Sul')]
# Urna clocks run on local time; offset to Brasília time in hours (no DST in 2026).
TZ_OFFSET = {'AC': 2, 'AM': 1, 'RO': 1, 'RR': 1, 'MT': 1, 'MS': 1}
NAME_ALIASES = {'MUQUEMDOSAOFRANCISCO': 'MUQUEMDESAOFRANCISCO', 'SANTATEREZINHA': 'SANTATERESINHA'}

VOTE_T0, VOTE_STEP, FAST_STEP = 8 * 3600, 120, 600
VOTE_END = 19 * 3600 + 30 * 60  # last vote bucket edge (19:30)
FAST_BINS = {'fp': [20, 25, 30, 40, 60, None], 'rel': [5, 8, 10, 15, 20, None], 'vote': [3, 4, 5, 6, 8, 10, None]}
FAST_DEFAULTS = {'fp': 2, 'rel': 2, 'vote': 2}   # <=30 s, <=10 s, <=5 s


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'[^A-Z]', '', s)
    return NAME_ALIASES.get(s, s)


def to_bins(v, edges):
    out = np.full(len(v), len(edges) - 1, dtype=np.int8)
    for i in range(len(edges) - 2, -1, -1):
        out[v <= edges[i]] = i
    return out


def secs_of_day(ts, day):
    """Timestamp -> seconds since 00:00 of the election day (can exceed 86400 for the next day)."""
    t = pd.to_datetime(ts, errors='coerce')
    return ((t - pd.Timestamp(day)).dt.total_seconds()).fillna(-1).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uf', required=True); ap.add_argument('--bweb', required=True); ap.add_argument('--logs', required=True)
    ap.add_argument('--geo-mun', required=True); ap.add_argument('--states-geo', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--day', default='2026-10-25'); ap.add_argument('--turno', default='2')
    ap.add_argument('--cargo', default='Presidente'); ap.add_argument('--sources', default=None)
    ap.add_argument('--notes', default=None, help='JSON {"zona/secao": "explanation"} for urnas whose log differs from the BU')
    a = ap.parse_args()
    uf = a.uf; off = TZ_OFFSET.get(uf, 0) * 3600
    out_data = os.path.join(a.out, 'data'); os.makedirs(os.path.join(out_data, uf, 'fast'), exist_ok=True)
    os.makedirs(os.path.join(a.out, 'geo'), exist_ok=True)

    # ---------------------------------------------------------------- BU (one row per urna)
    bw = pd.read_csv(a.bweb, sep=';', encoding='latin1', dtype=str)
    bw = bw[bw.DS_CARGO_PERGUNTA == a.cargo]
    for c in ['QT_APTOS', 'QT_COMPARECIMENTO', 'QT_VOTOS', 'QT_ELEI_BIOM_SEM_HABILITACAO']: bw[c] = pd.to_numeric(bw[c])
    key = ['NR_ZONA', 'NR_SECAO']
    cands = (bw[bw.DS_TIPO_VOTAVEL == 'Nominal'].groupby('NM_VOTAVEL').QT_VOTOS.sum().sort_values(ascending=False).index.tolist())
    pv = bw.pivot_table(index=key, columns='NM_VOTAVEL', values='QT_VOTOS', aggfunc='sum', fill_value=0)
    u = bw.drop_duplicates(key).set_index(key)[['CD_MUNICIPIO', 'NM_MUNICIPIO', 'NR_LOCAL_VOTACAO', 'QT_APTOS', 'QT_COMPARECIMENTO',
                                              'QT_ELEI_BIOM_SEM_HABILITACAO', 'DT_ABERTURA', 'DT_ENCERRAMENTO', 'DT_BU_RECEBIDO']].join(pv).reset_index()
    u['open'] = secs_of_day(u.DT_ABERTURA, a.day) + off
    u['close'] = secs_of_day(u.DT_ENCERRAMENTO, a.day) + off
    u['recv'] = secs_of_day(u.DT_BU_RECEBIDO, a.day)            # TSE server time (Brasília)

    # ---------------------------------------------------------------- municipalities & geometry
    geo = json.load(open(a.geo_mun))
    ib = {norm(f['properties']['name']): f for f in geo['features']}
    munis = u.groupby('CD_MUNICIPIO').agg(name=('NM_MUNICIPIO', 'first'), aptos=('QT_APTOS', 'sum'), urnas=('NR_SECAO', 'size')).reset_index()
    munis['ibge'] = munis.name.map(lambda n: ib.get(norm(n), {}).get('properties', {}).get('id'))
    missing = munis[munis.ibge.isna()]
    if len(missing): raise SystemExit(f'unmatched municipalities: {missing.name.tolist()}')
    from shapely.geometry import shape
    from shapely.validation import make_valid
    def label_point(g):
        g = make_valid(shape(g))
        if g.is_empty: raise SystemExit('empty municipal geometry')
        return g.representative_point() if not g.representative_point().is_empty else g.centroid
    rp = {f['properties']['id']: label_point(f['geometry']) for f in geo['features']}
    munis['lon'] = munis.ibge.map(lambda i: round(rp[i].x, 4)); munis['lat'] = munis.ibge.map(lambda i: round(rp[i].y, 4))
    # nicer display names from the geometry file (accents/case), TSE names are upper-case
    munis['display'] = munis.ibge.map(lambda i: next(f['properties']['name'] for f in geo['features'] if f['properties']['id'] == i))
    munis = munis.sort_values('display').reset_index(drop=True)
    midx = {c: i for i, c in enumerate(munis.CD_MUNICIPIO)}
    u['m'] = u.CD_MUNICIPIO.map(midx)

    # ---------------------------------------------------------------- logs
    n_vote = (VOTE_END - VOTE_T0) // VOTE_STEP; n_fast = (VOTE_END - VOTE_T0) // FAST_STEP
    series = {k: np.zeros((len(munis), n_vote), dtype=np.int64) for k in ['votes', 'manual', 'nofp']}
    fast_rows_m, fast_rows_b, models, val = [], [], [], {'urnas': 0, 'ok_votes': 0, 'ok_manual': 0, 'missing_log': 0, 'mismatch': []}
    per_mun = {i: {'series': [], 'manual': [], 'bio': []} for i in range(len(munis))}
    model_idx = {}
    phase_samples = {'fp': [], 'rel': [], 'vote_manual': [], 'vote_bio': []}
    u['model'] = -1; u['nofp'] = 0
    files = {os.path.basename(p)[:-8]: p for p in glob.glob(os.path.join(a.logs, '*.parquet'))}
    # file names in the TSE zip: o0322<pleito digit><uf><mun:5><zona:4><secao:4>-log.jez ; match on the numeric tail
    tail = {re.sub(r'^o\d+[a-z]{2}', '', k): k for k in files}
    for r in u.itertuples():
        val['urnas'] += 1
        k = tail.get(f"{int(r.CD_MUNICIPIO):05d}{int(r.NR_ZONA):04d}{int(r.NR_SECAO):04d}-log.jez")
        if k is None: val['missing_log'] += 1; continue
        t = pq.read_table(files[k]); meta = json.loads(t.schema.metadata[b'meta'])
        mdl = meta.get('model') or '?'
        if mdl not in model_idx: model_idx[mdl] = len(model_idx); models.append(mdl)
        u.at[r.Index, 'model'] = model_idx[mdl]
        v = t.to_pandas(); v = v[v.t_vote >= 0]
        for c in [c for c in v.columns if c.startswith('t_')]: v.loc[v[c] >= 0, c] += off
        manual = v.manual.values; bio = (v.hab_type == 'biométrica').values & ~manual; nofp = ~manual & ~bio
        if len(v) == r.QT_COMPARECIMENTO: val['ok_votes'] += 1
        if manual.sum() == r.QT_ELEI_BIOM_SEM_HABILITACAO: val['ok_manual'] += 1
        if len(v) != r.QT_COMPARECIMENTO or manual.sum() != r.QT_ELEI_BIOM_SEM_HABILITACAO:
            val['mismatch'].append({'zona': r.NR_ZONA, 'secao': r.NR_SECAO, 'bu_votes': int(r.QT_COMPARECIMENTO), 'log_votes': int(len(v)),
                                    'bu_manual': int(r.QT_ELEI_BIOM_SEM_HABILITACAO), 'log_manual': int(manual.sum())})
        u.at[r.Index, 'nofp'] = int(nofp.sum())
        vb = np.clip((v.t_vote.values - VOTE_T0) // VOTE_STEP, 0, n_vote - 1)
        fb = np.clip((v.t_vote.values - VOTE_T0) // FAST_STEP, 0, n_fast - 1)
        m = r.m
        np.add.at(series['votes'][m], vb, 1); np.add.at(series['manual'][m], vb[manual], 1); np.add.at(series['nofp'][m], vb[nofp], 1)
        vote_s = (v.t_vote - v.t_hab).values
        fp_s = np.where(v.t_fp_first.values >= 0, v.t_manual.values - v.t_fp_first.values, 0)
        rel_s = np.where(v.t_mesario.values >= 0, v.t_mesario.values - v.t_manual.values, 10 ** 6)
        vbin = to_bins(vote_s, FAST_BINS['vote']); fbin = to_bins(fp_s, FAST_BINS['fp']); rbin = to_bins(rel_s, FAST_BINS['rel'])
        ui = r.Index
        phase_samples['fp'].append(fp_s[manual & (v.t_fp_first.values >= 0)]); phase_samples['rel'].append(rel_s[manual & (v.t_mesario.values >= 0)])
        phase_samples['vote_manual'].append(vote_s[manual]); phase_samples['vote_bio'].append(vote_s[bio])
        if manual.any():
            fast_rows_m.append(pd.DataFrame({'m': m, 'u': ui, 'tb': fb[manual], 'fp': fbin[manual], 'rel': rbin[manual], 'vote': vbin[manual]}))
        if bio.any():
            fast_rows_b.append(pd.DataFrame({'m': m, 'u': ui, 'tb': fb[bio], 'vote': vbin[bio]}))
        sv = np.bincount(fb, minlength=n_fast); sm = np.bincount(fb[manual], minlength=n_fast)
        per_mun[m]['series'].append((ui, sv.tolist(), sm.tolist()))

    FM = pd.concat(fast_rows_m) if fast_rows_m else pd.DataFrame(columns=['m', 'u', 'tb', 'fp', 'rel', 'vote'])
    FB = pd.concat(fast_rows_b) if fast_rows_b else pd.DataFrame(columns=['m', 'u', 'tb', 'vote'])
    col = lambda df: {c: df[c].astype(int).tolist() for c in df.columns}
    st_m = FM.groupby(['m', 'tb', 'fp', 'rel', 'vote']).size().rename('n').reset_index()
    st_b = FB.groupby(['m', 'tb', 'vote']).size().rename('n').reset_index()

    # ---------------------------------------------------------------- per-municipality urna-level files
    for m in range(len(munis)):
        fm = FM[FM.m == m].groupby(['u', 'tb', 'fp', 'rel', 'vote']).size().rename('n').reset_index()
        fbm = FB[FB.m == m].groupby(['u', 'tb', 'vote']).size().rename('n').reset_index()
        s = per_mun[m]['series']
        json.dump({'manual': col(fm), 'bio': col(fbm),
                   'series': {'u': [x[0] for x in s], 'votes': [x[1] for x in s], 'manual': [x[2] for x in s]}},
                  open(os.path.join(out_data, uf, 'fast', f"{munis.ibge[m]}.json"), 'w'), separators=(',', ':'))

    # ---------------------------------------------------------------- state file
    cand_cols = {'lula': 'LULA', 'flavio': 'FLAVIO BOLSONARO'}   # BU names (NM_VOTAVEL), mapped explicitly
    for c in cand_cols.values():
        if c not in u.columns: raise SystemExit(f'candidate column {c} not found in BU; candidates: {cands}')
    urnas = {
        'm': u.m.astype(int).tolist(), 'z': u.NR_ZONA.astype(int).tolist(), 's': u.NR_SECAO.astype(int).tolist(),
        'loc': u.NR_LOCAL_VOTACAO.astype(int).tolist(), 'aptos': u.QT_APTOS.astype(int).tolist(), 'comp': u.QT_COMPARECIMENTO.astype(int).tolist(),
        'manual': u.QT_ELEI_BIOM_SEM_HABILITACAO.clip(lower=0).astype(int).tolist(),
        'nofp': u.nofp.astype(int).tolist(), 'open': u.open.astype(int).tolist(), 'close': u.close.astype(int).tolist(), 'recv': u.recv.astype(int).tolist(),
        'lula': u[cand_cols['lula']].astype(int).tolist(), 'flavio': u[cand_cols['flavio']].astype(int).tolist(),
        'branco': u.get('Branco', 0).astype(int).tolist(), 'nulo': u.get('Nulo', 0).astype(int).tolist(), 'model': u.model.astype(int).tolist(),
    }
    state = {
        'uf': uf,
        'munis': {'ibge': munis.ibge.tolist(), 'tse': munis.CD_MUNICIPIO.tolist(), 'name': munis.display.tolist(),
                  'aptos': munis.aptos.astype(int).tolist(), 'urnas': munis.urnas.astype(int).tolist(), 'lon': munis.lon.tolist(), 'lat': munis.lat.tolist()},
        'series': {k: v.tolist() for k, v in series.items()},
        'urnas': urnas, 'models': models,
        'fast': {'manual': col(st_m), 'bio': col(st_b)},
        'candidates': cands[:2],
    }
    json.dump(state, open(os.path.join(out_data, f'{uf}.json'), 'w'), separators=(',', ':'))
    json.dump(geo, open(os.path.join(a.out, 'geo', f'{uf}_mun.json'), 'w'), separators=(',', ':'))

    # ---------------------------------------------------------------- markers (data-derived where stated)
    closes = u.close[u.close >= 0]
    normal = closes[closes < 18 * 3600]
    ext_start = int(np.percentile(normal, 99)) if len(normal) else 17 * 3600
    recv = u.recv[u.recv >= 0]
    markers = [
        {'key': 'open', 'short': 'Abertura', 't': 8 * 3600, 'label': 'Início da votação', 'desc': 'Horário oficial de abertura (08:00, horário de Brasília).'},
        {'key': 'close_regular', 'short': 'Encerr.', 't': 17 * 3600, 'label': 'Encerramento regular', 'desc': 'Horário oficial de encerramento (17:00). Eleitores já na fila ainda votam.'},
        {'key': 'ext_start', 'short': 'Além filas', 't': ext_start, 'label': 'Urnas além das filas', 'desc': 'Calculado dos dados: horário em que 99% das urnas que encerraram antes das 18:00 já estavam encerradas. Depois dele, as urnas abertas são as que funcionaram além das filas normais (prorrogação).'},
        {'key': 'ext_end', 'short': 'Fim prorr.', 't': int(closes.max()), 'label': 'Fim da prorrogação', 'desc': 'Calculado dos dados: encerramento da última urna (campo DT_ENCERRAMENTO do BU).'},
        {'key': 'first_bu', 'short': '1º BU', 't': int(recv.min()), 'label': '1º BU recebido', 'desc': 'Primeiro Boletim de Urna recebido pelo TSE (DT_BU_RECEBIDO).'},
        {'key': 'last_bu', 'short': 'Fim apur.', 't': int(recv.max()), 'label': 'Fim da apuração', 'desc': 'Último Boletim de Urna recebido pelo TSE (DT_BU_RECEBIDO).'},
    ]

    # ---------------------------------------------------------------- states geometry + manifest
    sg = json.load(open(a.states_geo))
    meta_by_code = {c: (s, n, r) for c, s, n, r in STATES}
    for f in sg['features']:
        code = f['properties']['uf']; s, n, r = meta_by_code[code]
        f['properties'] = {'uf': s, 'code': code, 'name': n, 'region': r}
    json.dump(sg, open(os.path.join(a.out, 'geo', 'br_states.json'), 'w'), separators=(',', ':'))

    notes = json.load(open(a.notes)) if a.notes else {}
    mpath = os.path.join(out_data, 'manifest.json')
    man = json.load(open(mpath)) if os.path.exists(mpath) else {}
    loaded = set(man.get('loaded', [])) | {uf}
    cand_meta = {'lula': {'key': 'lula', 'name': 'Lula', 'short': 'Lula', 'number': 13, 'party': 'PT'},
                 'flavio': {'key': 'flavio', 'name': 'Flávio Bolsonaro', 'short': 'Flávio', 'number': 22, 'party': 'PL'}}
    t_end = int(np.ceil((recv.max() + 900) / 900) * 900)
    man.update({
        'generated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'election': {'label': f'Eleições 2026 · {a.turno}º turno · {a.cargo} · horário de Brasília', 'day': a.day,
                     'candidates': [cand_meta['lula'], cand_meta['flavio']]},
        'time': {'start': 7 * 3600 + 30 * 60, 'end': max(t_end, man.get('time', {}).get('end', 0)), 'vote_t0': VOTE_T0, 'vote_step': VOTE_STEP,
                 'vote_n': int(n_vote), 'fast_step': FAST_STEP, 'fast_n': int(n_fast)},
        'markers': markers,  # TODO when several states are loaded: recompute markers over all of them
        'fast_bins': {**FAST_BINS, 'defaults': FAST_DEFAULTS},
        'fast_medians': {k: float(np.median(np.concatenate(v))) if v else None for k, v in phase_samples.items()},
        'regions': [{'key': k, 'name': n, 'ufs': [s for c, s, _, r in STATES if r == k]} for k, n in REGIONS],
        'states': [{'uf': s, 'code': c, 'name': n, 'region': r, 'loaded': s in loaded,
                    'file': f'data/{s}.json', 'geo': f'geo/{s}_mun.json'} for c, s, n, r in STATES],
        'loaded': sorted(loaded),
        'geo': {'states': 'geo/br_states.json'},
        'validation': f"{uf}: {val['ok_votes']} de {val['urnas']} urnas com votos do log = comparecimento do BU; "
                      f"{val['ok_manual']} de {val['urnas']} com habilitações manuais do log = 'não habilitados por biometria' do BU"
                      + (f"; {val['missing_log']} urnas sem log" if val['missing_log'] else '') + '.',
        'sources': json.load(open(a.sources)) if a.sources else man.get('sources', []),
        'discrepancies': [d for d in man.get('discrepancies', []) if d.get('uf') != uf] + [
            {**d, 'uf': uf, 'note': notes.get(f"{d['zona']}/{d['secao']}", '')} for d in val['mismatch']],
    })
    json.dump(man, open(mpath, 'w'), ensure_ascii=False, indent=1)
    json.dump(val, open(os.path.join(out_data, uf, 'validation.json'), 'w'), indent=1)
    print(json.dumps({k: (v if k != 'mismatch' else len(v)) for k, v in val.items()}))
    print('markers:', [(m['key'], f"{m['t']//3600:02d}:{m['t']%3600//60:02d}") for m in markers])


if __name__ == '__main__':
    main()
