"""Build site/data/manifest.json from every state's summary.json (national markers, medians, validation).

usage: python finalize_manifest.py site/
"""
import datetime as dt, glob, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
from build_site_data import VOTE_T0, VOTE_STEP, FAST_STEP, VOTE_END, FAST_BINS  # noqa: E402

FAST_DEFAULTS = {'fp': 2, 'rel': 2, 'vote': 2}   # <=30 s, <=10 s, <=5 s
GENERAL_SOURCES = [
    {'label': 'Portal de Dados Abertos do TSE · Resultados 2026 · Boletim de Urna',
     'url': 'https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna'},
    {'label': 'Portal de Dados Abertos do TSE · Resultados 2026 · Arquivos transmitidos para totalização',
     'url': 'https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao'},
    {'label': 'Malhas municipais (geodata-br, derivadas do IBGE)', 'url': 'https://github.com/tbrugz/geodata-br',
     'note': 'Simplificadas com mapshaper para a web.'},
]


def median_from_hist(h):
    h = np.asarray(h); c = np.cumsum(h)
    return float(np.searchsorted(c, c[-1] / 2)) if c[-1] else None


def main():
    out = sys.argv[1]
    sums = {json.load(open(p))['uf']: json.load(open(p)) for p in glob.glob(os.path.join(out, 'data', '*', 'summary.json'))}
    loaded = sorted(sums)
    hist = {}
    for s in sums.values():
        for k, v in s['normal_close_hist'].items(): hist[int(k)] = hist.get(int(k), 0) + v
    mins = np.repeat(np.array(sorted(hist)), [hist[k] for k in sorted(hist)])
    ext_start = int(np.percentile(mins, 99) * 60) if len(mins) else 17 * 3600
    # all closing times (Brasília) from the state files, to place the end of the extension robustly
    import gzip
    closes, last = [], None
    for uf in loaded:
        d = json.load(gzip.open(os.path.join(out, 'data', f'{uf}.json.gz')))
        u = d['urnas']
        for k, c in enumerate(u['close']):
            if c < 0: continue
            closes.append(c)
            if last is None or c > last[0]: last = (c, uf, d['munis']['name'][u['m'][k]], u['z'][k], u['s'][k], u['comp'][k])
    closes = np.sort(np.array(closes))
    ext_end = int(closes[int(np.ceil(len(closes) * 0.9999)) - 1])
    last_close = last[0]
    first_bu = min(s['first_bu'] for s in sums.values() if s['first_bu'])
    last_bu = max(s['last_bu'] for s in sums.values() if s['last_bu'])
    scope = 'todas as urnas carregadas' if len(loaded) > 1 else f'urnas de {loaded[0]}'
    markers = [
        {'key': 'open', 'short': 'Abertura', 't': 8 * 3600, 'label': 'Início da votação', 'desc': 'Horário oficial de abertura (08:00, horário de Brasília).'},
        {'key': 'close_regular', 'short': 'Encerr.', 't': 17 * 3600, 'label': 'Encerramento regular', 'desc': 'Horário oficial de encerramento (17:00, horário de Brasília). Eleitores já na fila ainda votam.'},
        {'key': 'ext_start', 'short': 'Além filas', 't': ext_start, 'label': 'Urnas além das filas', 'desc': f'Calculado dos dados ({scope}): minuto em que 99% das urnas que encerraram antes das 18:00 já estavam encerradas. Depois dele, as urnas abertas são as que funcionaram além das filas normais (prorrogação).'},
        {'key': 'ext_end', 'short': 'Fim prorr.', 't': ext_end, 'label': 'Fim da prorrogação', 'desc': f'Calculado dos dados ({scope}): minuto em que 99,99% das urnas já estavam encerradas (DT_ENCERRAMENTO do BU, no horário de Brasília). Restavam {int((closes > ext_end).sum())} urnas abertas.'},
        {'key': 'last_close', 'short': 'Última urna', 't': last_close, 'label': 'Última urna encerrada', 'desc': f'{last[2]} ({last[1]}), zona {last[3]}, seção {last[4]}: encerrou às {last[0]//3600:02d}:{last[0]%3600//60:02d}:{last[0]%60:02d} com {last[5]} votos.'},
        {'key': 'first_bu', 'short': '1º BU', 't': first_bu, 'label': '1º BU recebido', 'desc': 'Primeiro Boletim de Urna recebido pelo TSE (DT_BU_RECEBIDO).'},
        {'key': 'last_bu', 'short': 'Fim apur.', 't': last_bu, 'label': 'Fim da apuração', 'desc': 'Último Boletim de Urna recebido pelo TSE (DT_BU_RECEBIDO).'},
    ]
    ph = {}
    for s in sums.values():
        for k, v in s['phase_hist'].items(): ph[k] = np.add(ph.get(k, 0), v)
    val_lines, tot = [], {'urnas': 0, 'ok_votes': 0, 'ok_manual': 0}
    for uf in loaded:
        v = sums[uf]['validation']
        for k in tot: tot[k] += v[k]
        val_lines.append({'uf': uf, **v})
    sources = list(GENERAL_SOURCES)
    for uf in loaded: sources += sums[uf]['sources']
    man = {
        'generated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'election': {'label': 'Eleições 2026 · 2º turno · Presidente · horário de Brasília', 'day': '2026-10-25',
                     'candidates': [{'key': 'lula', 'name': 'Lula', 'short': 'Lula', 'number': 13, 'party': 'PT'},
                                    {'key': 'flavio', 'name': 'Flávio Bolsonaro', 'short': 'Flávio', 'number': 22, 'party': 'PL'}]},
        'time': {'start': 7 * 3600 + 30 * 60, 'end': int(np.ceil((last_bu + 900) / 900) * 900), 'vote_t0': VOTE_T0, 'vote_step': VOTE_STEP,
                 'vote_n': (VOTE_END - VOTE_T0) // VOTE_STEP, 'fast_step': FAST_STEP, 'fast_n': (VOTE_END - VOTE_T0) // FAST_STEP},
        'markers': markers,
        'fast_bins': {**FAST_BINS, 'defaults': FAST_DEFAULTS},
        'fast_medians': {k: median_from_hist(v) for k, v in ph.items()},
        'regions': [{'key': k, 'name': n, 'ufs': [s for c, s, _, r in STATES if r == k]} for k, n in REGIONS],
        'states': [{'uf': s, 'code': c, 'name': n, 'region': r, 'loaded': s in sums,
                    'file': f'data/{s}.json.gz', 'geo': f'geo/{s}_mun.json.gz',
                    'urnas': sums[s]['urnas'] if s in sums else None} for c, s, n, r in STATES],
        'loaded': loaded,
        'geo': {'states': 'geo/br_states.json'},
        'validation': (f"{tot['ok_votes']:,} de {tot['urnas']:,} urnas com votos do log = comparecimento do BU; "
                       f"{tot['ok_manual']:,} de {tot['urnas']:,} com habilitações manuais do log = 'não habilitados por biometria' do BU.").replace(',', '.'),
        'validation_by_state': val_lines,
        'discrepancies': [d for uf in loaded for d in sums[uf]['discrepancies']],
        'sources': sources,
    }
    json.dump(man, open(os.path.join(out, 'data', 'manifest.json'), 'w'), ensure_ascii=False, indent=1)
    print('states:', len(loaded), '| markers:', [(m['key'], f"{m['t']//3600:02d}:{m['t']%3600//60:02d}") for m in markers])
    print(man['validation'], '| discrepancies:', len(man['discrepancies']))


if __name__ == '__main__':
    main()
