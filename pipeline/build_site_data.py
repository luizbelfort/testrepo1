"""Build the static site's data files for one state from:
  - the BU CSV (bweb_<turno>_<UF>_*.csv) published by the TSE,
  - the parsed urna logs produced by run_full.py (batch_*.parquet + meta_*.jsonl, or older per-urna parquet),
  - simplified municipal boundaries (prep_geo.py).

Nothing is estimated: every count is a direct aggregation of the published files. Each urna's log is
checked against its BU (voters and "não habilitados por biometria"); mismatches are reported.
Run finalize_manifest.py afterwards to (re)build the national manifest from all state summaries.

usage: python build_site_data.py --uf BA --bweb <csv> --logs <dir> --geo-mun <geojson> --out site/ [--sources s.json] [--notes n.json]
"""
import argparse, difflib, glob, gzip, json, os, re, unicodedata
import numpy as np, pandas as pd, pyarrow.parquet as pq

# TSE name -> name in the boundary file, per state (renamed municipalities; names repeat across states)
NAME_ALIASES = {
    'BA': {'MUQUEMDOSAOFRANCISCO': 'MUQUEMDESAOFRANCISCO', 'SANTATEREZINHA': 'SANTATERESINHA'},
    'TO': {'TABOCAO': 'FORTALEZADOTABOCAO', 'SAOVALERIO': 'SAOVALERIODANATIVIDADE'},
    'PB': {'JOCACLAUDINO': 'SANTAREM', 'SAOVICENTEDOSERIDO': 'SERIDO', 'TACIMA': 'CAMPODESANTANA'},
    'RN': {'ASSU': 'ACU', 'AREZ': 'ARES', 'CAMPOGRANDE': 'AUGUSTOSEVERO', 'BOASAUDE': 'JANUARIOCICCO', 'SERRACAIADA': 'PRESIDENTEJUSCELINO'},
    'GO': {'BOMJESUS': 'BOMJESUSDEGOIAS'},
    'SP': {'EMBUDASARTES': 'EMBU'},
}
VOTE_T0, VOTE_STEP, FAST_STEP = 8 * 3600, 120, 600
VOTE_END = 21 * 3600                      # last vote bucket edge (21:00 Brasília)
FAST_BINS = {'fp': [20, 25, 30, 40, 60, None], 'rel': [5, 8, 10, 15, 20, None], 'vote': [3, 4, 5, 6, 8, 10, None]}
PHASE_MAX = 600                           # histogram cap (s) used for medians
KEEP_T = ['t_id', 't_fp_first', 't_manual', 't_mes_req', 't_mesario', 't_hab', 't_vote']


def norm(s, uf=None):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'[^A-Z]', '', s)
    return NAME_ALIASES.get(uf, {}).get(s, s) if uf else s


def to_bins(v, edges):
    out = np.full(len(v), len(edges) - 1, dtype=np.int8)
    for i in range(len(edges) - 2, -1, -1):
        out[v <= edges[i]] = i
    return out


def secs_of_day(ts, day):
    t = pd.to_datetime(ts, errors='coerce')
    return ((t - pd.Timestamp(day)).dt.total_seconds()).fillna(-1).astype(int)


def dump_gz(obj, path):
    with gzip.open(path, 'wt', encoding='utf-8', compresslevel=9) as fh:
        json.dump(obj, fh, separators=(',', ':'), ensure_ascii=False, allow_nan=False)   # NaN is not valid JSON


def load_logs(d):
    # batches are read oldest first; if an urna was reprocessed, only its newest batch is kept
    frames, metas, owner = [], [], {}
    batches = sorted(glob.glob(os.path.join(d, 'batch_*.parquet')), key=os.path.getmtime)
    for p in batches:
        mp = p.replace('batch_', 'meta_').replace('.parquet', '.jsonl')
        for l in open(mp):
            m = json.loads(l); owner[m['fname']] = p; metas.append(m)
    metas = list({m['fname']: m for m in metas}.values())
    for p in batches:
        df = pq.read_table(p).to_pandas()
        frames.append(df[df.fname.map(owner).values == p])
    old = sorted(glob.glob(os.path.join(d, '*-log.jez.parquet')))
    old = [p for p in old if os.path.basename(p)[:-8] not in owner]   # reprocessed in a newer batch
    for p in old:                                   # older one-file-per-urna format (meta in schema metadata)
        t = pq.read_table(p); fn = os.path.basename(p)[:-8]
        m = json.loads(t.schema.metadata[b'meta']); m['fname'] = fn; metas.append(m)
        df = t.to_pandas(); df['fname'] = fn; frames.append(df)
    V = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if 'recovered' not in V: V['recovered'] = False
    V['recovered'] = V['recovered'].fillna(False).astype(bool)
    return V, pd.DataFrame(metas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uf', required=True); ap.add_argument('--bweb', required=True); ap.add_argument('--logs', required=True)
    ap.add_argument('--geo-mun', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--day', default='2026-10-25'); ap.add_argument('--cargo', default='Presidente')
    ap.add_argument('--sources', default=None); ap.add_argument('--notes', default=None)
    a = ap.parse_args()
    uf = a.uf
    out_data = os.path.join(a.out, 'data'); fast_dir = os.path.join(out_data, uf, 'fast')
    os.makedirs(fast_dir, exist_ok=True); os.makedirs(os.path.join(a.out, 'geo'), exist_ok=True)
    for old in glob.glob(os.path.join(fast_dir, '*')): os.remove(old)

    # ---------------------------------------------------------------- BU (one row per urna)
    bw = pd.read_csv(a.bweb, sep=';', encoding='latin1', dtype=str)
    bw = bw[bw.DS_CARGO_PERGUNTA == a.cargo]
    for c in ['QT_APTOS', 'QT_COMPARECIMENTO', 'QT_VOTOS', 'QT_ELEI_BIOM_SEM_HABILITACAO']: bw[c] = pd.to_numeric(bw[c])
    key = ['NR_ZONA', 'NR_SECAO']
    pv = bw.pivot_table(index=key, columns='NM_VOTAVEL', values='QT_VOTOS', aggfunc='sum', fill_value=0)
    u = bw.drop_duplicates(key).set_index(key)[['CD_MUNICIPIO', 'NM_MUNICIPIO', 'NR_LOCAL_VOTACAO', 'QT_APTOS', 'QT_COMPARECIMENTO',
                                              'QT_ELEI_BIOM_SEM_HABILITACAO', 'DT_ABERTURA', 'DT_ENCERRAMENTO', 'DT_BU_RECEBIDO']].join(pv).reset_index()
    cand_cols = {'lula': 'LULA', 'flavio': 'FLAVIO BOLSONARO'}   # BU names (NM_VOTAVEL), mapped explicitly
    for c in list(cand_cols.values()) + ['Branco', 'Nulo']:
        if c not in u.columns: raise SystemExit(f'{uf}: column {c} not found in BU')

    # Urna clocks run on local time. Urnas open at 08:00 Brasília, so the local opening hour of a
    # municipality's urnas gives its offset (data-derived; covers AC, AM-west, MT, MS, RO, RR, Noronha...).
    oh = pd.to_datetime(u.DT_ABERTURA, errors='coerce')
    u['open_h'] = oh.dt.hour + (oh.dt.minute >= 45)      # an urna opening at 07:5x counts as 08
    mode_h = u[oh.dt.minute.between(0, 59)].groupby('CD_MUNICIPIO').open_h.agg(lambda x: x.mode().iloc[0])
    u['tz'] = (8 - u.CD_MUNICIPIO.map(mode_h).fillna(8)).clip(-1, 3).astype(int) * 3600
    u['open'] = np.where(secs_of_day(u.DT_ABERTURA, a.day) >= 0, secs_of_day(u.DT_ABERTURA, a.day) + u.tz, -1)
    u['close'] = np.where(secs_of_day(u.DT_ENCERRAMENTO, a.day) >= 0, secs_of_day(u.DT_ENCERRAMENTO, a.day) + u.tz, -1)
    u['recv'] = secs_of_day(u.DT_BU_RECEBIDO, a.day)            # TSE server time (Brasília)
    u['key'] = [f"{int(m):05d}{int(z):04d}{int(s):04d}" for m, z, s in zip(u.CD_MUNICIPIO, u.NR_ZONA, u.NR_SECAO)]

    # ---------------------------------------------------------------- municipalities & geometry
    geo = json.load(open(a.geo_mun))
    gfeat = {f['properties']['id']: f for f in geo['features']}
    ib = {norm(f['properties']['name']): f['properties']['id'] for f in geo['features']}
    munis = u.groupby('CD_MUNICIPIO').agg(name=('NM_MUNICIPIO', 'first'), aptos=('QT_APTOS', 'sum'), urnas=('NR_SECAO', 'size'),
                                          tz=('tz', 'first')).reset_index()
    matched, fuzzy, nogeo = [], [], []
    for n in munis.name:
        k = norm(n, uf)
        if k in ib: matched.append(ib[k]); continue
        best = difflib.get_close_matches(k, list(ib), n=1, cutoff=0.85)
        if best:
            matched.append(ib[best[0]]); fuzzy.append((n, gfeat[ib[best[0]]]['properties']['name']))
        else:
            matched.append(None); nogeo.append(n)
    got = [i for i in matched if i]
    if len(got) != len(set(got)): raise SystemExit(f'{uf}: two TSE municipalities matched the same shape')
    munis['ibge'] = [i if i else f'TSE{c}' for i, c in zip(matched, munis.CD_MUNICIPIO)]   # no shape: keep data, id from TSE code
    from shapely.geometry import shape
    from shapely.validation import make_valid
    def label_point(i):
        if i not in gfeat: return (None, None)
        g = make_valid(shape(gfeat[i]['geometry'])); p = g.representative_point()
        return (round(p.x, 4), round(p.y, 4))
    pts = munis.ibge.map(label_point)
    munis['lon'] = [p[0] for p in pts]; munis['lat'] = [p[1] for p in pts]
    munis['display'] = [gfeat[i]['properties']['name'] if i in gfeat else n.title() for i, n in zip(munis.ibge, munis.name)]
    munis = munis.sort_values('display').reset_index(drop=True)
    u['m'] = u.CD_MUNICIPIO.map({c: i for i, c in enumerate(munis.CD_MUNICIPIO)})

    # ---------------------------------------------------------------- logs (vectorised)
    V, META = load_logs(a.logs)
    keyre = re.compile(r'(\d{13})-log\.jez$')
    ukey = {k: i for i, k in enumerate(u.key)}
    META['ui'] = META.fname.map(lambda f: ukey.get(keyre.search(f).group(1), -1))
    V['ui'] = V.fname.map(dict(zip(META.fname, META.ui))).fillna(-1).astype(int)
    V = V[(V.t_vote >= 0) & (V.ui >= 0)].reset_index(drop=True)
    tz = u.tz.values[V.ui.values]
    for c in KEEP_T:
        x = V[c].values.astype(np.int64); V[c] = np.where(x >= 0, x + tz, -1)
    has_log = np.zeros(len(u), bool); has_log[META.ui[META.ui >= 0].values] = True
    model = META[META.ui >= 0].set_index('ui').model.fillna('?')
    models = sorted(model.unique().tolist())
    u['model'] = [models.index(model[i]) if i in model.index else -1 for i in range(len(u))]
    cont = META[META.ui >= 0].set_index('ui')
    # A vote confirmed right before an urna restart has no "computado" line. Sometimes the BU counts it (power loss
    # after the vote was stored), sometimes not (voter voted again). The log alone cannot tell, so per urna we keep
    # such votes only if that is what makes the log agree with the BU; the count of dropped ones is reported.
    bu_comp = u.QT_COMPARECIMENTO.values
    n_all = np.bincount(V.ui.values, minlength=len(u)); n_rec = np.bincount(V.ui.values[V.recovered.values], minlength=len(u))
    drop_u = (n_rec > 0) & (n_all != bu_comp) & (n_all - n_rec == bu_comp)
    dropped_recovered = int(n_rec[drop_u].sum())
    V = V[~(V.recovered.values & drop_u[V.ui.values])].reset_index(drop=True)
    manual = V.manual.values.astype(bool); bio = (V.hab_type.values == 'biométrica') & ~manual; nofp = ~manual & ~bio
    ui = V.ui.values; nU = len(u)
    n_log = np.bincount(ui, minlength=nU); n_man = np.bincount(ui[manual], minlength=nU); n_nofp = np.bincount(ui[nofp], minlength=nU)
    u['nofp'] = n_nofp
    bu_v = u.QT_COMPARECIMENTO.values; bu_m = u.QT_ELEI_BIOM_SEM_HABILITACAO.clip(lower=0).values
    okv = has_log & (n_log == bu_v); okm = has_log & (n_man == bu_m)
    notes = json.load(open(a.notes)) if a.notes else {}
    mism = []
    for i in np.where(has_log & ~(okv & okm))[0]:
        r = u.iloc[i]; c = cont.loc[i] if i in cont.index else {}
        mism.append({'uf': uf, 'zona': str(r.NR_ZONA), 'secao': str(r.NR_SECAO), 'municipio': munis.display[r.m],
                     'bu_votes': int(bu_v[i]), 'log_votes': int(n_log[i]), 'bu_manual': int(bu_m[i]), 'log_manual': int(n_man[i]),
                     'contingency': bool(c.get('contingency', False)) if len(c) else False,
                     'restarts': int(c.get('restarts', 0) or 0) if len(c) else 0,
                     'note': notes.get(f'{r.NR_ZONA}/{r.NR_SECAO}', '')})
    for i in np.where(~has_log)[0]:
        r = u.iloc[i]
        mism.append({'uf': uf, 'zona': str(r.NR_ZONA), 'secao': str(r.NR_SECAO), 'municipio': munis.display[r.m],
                     'bu_votes': int(bu_v[i]), 'log_votes': 0, 'bu_manual': int(bu_m[i]), 'log_manual': 0, 'contingency': False, 'restarts': 0,
                     'note': notes.get(f'{r.NR_ZONA}/{r.NR_SECAO}', 'O log desta urna não está no pacote publicado pelo TSE.')})
    val = {'urnas': int(nU), 'with_log': int(has_log.sum()), 'ok_votes': int(okv.sum()), 'ok_manual': int(okm.sum()),
           'recovered_votes_kept': int(V.recovered.sum()), 'recovered_votes_dropped': dropped_recovered, 'mismatch': mism,
           'fuzzy_names': fuzzy, 'no_geometry': nogeo, 'tz_offsets_h': {str(k // 3600): int(v) for k, v in munis.tz.value_counts().items()}}

    m = u.m.values[ui]; nM = len(munis)
    n_vote = (VOTE_END - VOTE_T0) // VOTE_STEP; n_fast = (VOTE_END - VOTE_T0) // FAST_STEP
    vb = np.clip((V.t_vote.values - VOTE_T0) // VOTE_STEP, 0, n_vote - 1)
    fb = np.clip((V.t_vote.values - VOTE_T0) // FAST_STEP, 0, n_fast - 1)
    grid = lambda mask: np.bincount(m[mask] * n_vote + vb[mask], minlength=nM * n_vote).reshape(nM, n_vote)
    series = {'votes': grid(np.ones(len(V), bool)), 'manual': grid(manual), 'nofp': grid(nofp)}
    vote_s = V.t_vote.values - V.t_hab.values
    fp_s = np.where(V.t_fp_first.values >= 0, V.t_manual.values - V.t_fp_first.values, 0)
    rel_s = np.where(V.t_mesario.values >= 0, V.t_mesario.values - V.t_manual.values, 10 ** 6)
    vbin = to_bins(vote_s, FAST_BINS['vote']); fbin = to_bins(fp_s, FAST_BINS['fp']); rbin = to_bins(rel_s, FAST_BINS['rel'])
    hist = lambda x: np.bincount(np.clip(x, 0, PHASE_MAX), minlength=PHASE_MAX + 1).tolist()
    phase_hist = {'fp': hist(fp_s[manual & (V.t_fp_first.values >= 0)]), 'rel': hist(rel_s[manual & (V.t_mesario.values >= 0)]),
                  'vote_manual': hist(vote_s[manual]), 'vote_bio': hist(vote_s[bio])}

    FM = pd.DataFrame({'m': m[manual], 'u': ui[manual], 'tb': fb[manual], 'fp': fbin[manual], 'rel': rbin[manual], 'vote': vbin[manual]})
    FB = pd.DataFrame({'m': m[bio], 'tb': fb[bio], 'vote': vbin[bio]})
    col = lambda df: {c: df[c].astype(int).tolist() for c in df.columns}
    st_m = FM.groupby(['m', 'tb', 'fp', 'rel', 'vote']).size().rename('n').reset_index()
    st_b = FB.groupby(['m', 'tb', 'vote']).size().rename('n').reset_index()

    # ---------------------------------------------------------------- per-municipality urna-level files
    um = FM.groupby(['m', 'u', 'tb', 'fp', 'rel', 'vote']).size().rename('n').reset_index()
    sv = np.bincount(ui * n_fast + fb, minlength=nU * n_fast).reshape(nU, n_fast)
    sm = np.bincount(ui[manual] * n_fast + fb[manual], minlength=nU * n_fast).reshape(nU, n_fast)
    by_m = {k: g.drop(columns='m') for k, g in um.groupby('m')}
    urnas_of = u.groupby('m').groups
    for mi in range(nM):
        us = sorted(urnas_of.get(mi, []))
        g = by_m.get(mi, pd.DataFrame(columns=['u', 'tb', 'fp', 'rel', 'vote', 'n']))
        dump_gz({'manual': col(g), 'series': {'u': [int(x) for x in us], 'votes': sv[us].tolist(), 'manual': sm[us].tolist()}},
                os.path.join(fast_dir, f'{munis.ibge[mi]}.json.gz'))

    # ---------------------------------------------------------------- state file
    urnas = {
        'm': u.m.astype(int).tolist(), 'z': u.NR_ZONA.astype(int).tolist(), 's': u.NR_SECAO.astype(int).tolist(),
        'loc': u.NR_LOCAL_VOTACAO.astype(int).tolist(), 'aptos': u.QT_APTOS.astype(int).tolist(), 'comp': u.QT_COMPARECIMENTO.astype(int).tolist(),
        'manual': u.QT_ELEI_BIOM_SEM_HABILITACAO.clip(lower=0).astype(int).tolist(),
        'nofp': u.nofp.astype(int).tolist(), 'open': u.open.astype(int).tolist(), 'close': u.close.astype(int).tolist(), 'recv': u.recv.astype(int).tolist(),
        'lula': u[cand_cols['lula']].astype(int).tolist(), 'flavio': u[cand_cols['flavio']].astype(int).tolist(),
        'branco': u['Branco'].astype(int).tolist(), 'nulo': u['Nulo'].astype(int).tolist(), 'model': u.model.astype(int).tolist(),
    }
    state = {
        'uf': uf,
        'munis': {'ibge': munis.ibge.tolist(), 'tse': munis.CD_MUNICIPIO.tolist(), 'name': munis.display.tolist(),
                  'aptos': munis.aptos.astype(int).tolist(), 'urnas': munis.urnas.astype(int).tolist(),
                  'lon': [None if pd.isna(x) else float(x) for x in munis.lon], 'lat': [None if pd.isna(x) else float(x) for x in munis.lat],
                  'tz': (munis.tz // 3600).astype(int).tolist()},
        'series': {k: v.tolist() for k, v in series.items()},
        'urnas': urnas, 'models': models,
        'fast': {'manual': col(st_m), 'bio': col(st_b)},
    }
    dump_gz(state, os.path.join(out_data, f'{uf}.json.gz'))
    for f in geo['features']:   # only id + name are needed; source properties may contain NaN
        f['properties'] = {'id': f['properties']['id'], 'name': f['properties']['name']}
    dump_gz(geo, os.path.join(a.out, 'geo', f'{uf}_mun.json.gz'))

    # ---------------------------------------------------------------- summary (read by finalize_manifest.py)
    closes = u.close[u.close >= 0].values; recv = u.recv[u.recv >= 0].values
    normal = closes[closes < 18 * 3600]
    summary = {
        'uf': uf, 'urnas': int(nU), 'aptos': int(u.QT_APTOS.sum()), 'comparecimento': int(bu_v.sum()),
        'normal_close_hist': {int(k): int(v) for k, v in zip(*np.unique(normal // 60, return_counts=True))},
        'last_close': int(closes.max()) if len(closes) else None, 'first_bu': int(recv.min()) if len(recv) else None,
        'last_bu': int(recv.max()) if len(recv) else None, 'phase_hist': phase_hist, 'validation': {k: v for k, v in val.items() if k != 'mismatch'},
        'discrepancies': mism, 'sources': json.load(open(a.sources)) if a.sources else [],
    }
    json.dump(summary, open(os.path.join(out_data, uf, 'summary.json'), 'w'), ensure_ascii=False)
    print(json.dumps({k: v for k, v in val.items() if k not in ('mismatch',)} | {'mismatch': len(mism)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
