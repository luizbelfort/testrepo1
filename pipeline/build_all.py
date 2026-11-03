"""For every state whose logs are parsed (fetch_all.py), prepare geometry + sources and build its site data,
then rebuild the national manifest.

usage: python build_all.py <workdir> <site dir> <mapshaper bin> [UF,UF,...]
"""
import json, os, subprocess, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
W, SITE, MAPSHAPER = sys.argv[1:4]
ONLY = sys.argv[4].split(',') if len(sys.argv) > 4 else None
CODES = {'RO': '11', 'AC': '12', 'AM': '13', 'RR': '14', 'PA': '15', 'AP': '16', 'TO': '17', 'MA': '21', 'PI': '22', 'CE': '23',
         'RN': '24', 'PB': '25', 'PE': '26', 'AL': '27', 'SE': '28', 'BA': '29', 'MG': '31', 'ES': '32', 'RJ': '33', 'SP': '35',
         'PR': '41', 'SC': '42', 'RS': '43', 'MS': '50', 'MT': '51', 'GO': '52', 'DF': '53'}
GEO = 'https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-{code}-mun.json'


def sh(*a): return subprocess.run(list(a), check=True, capture_output=True, text=True).stdout


def prep_geo(uf, d):
    raw, out = os.path.join(d, 'mun_raw.json'), os.path.join(d, 'mun.json')
    if not os.path.exists(out):
        if not os.path.exists(raw): sh('curl', '-sSf', '-m', '300', '-o', raw, GEO.format(code=CODES[uf]))
        sh('node', MAPSHAPER, raw, '-clean', '-simplify', '8%', 'keep-shapes', '-o', 'precision=0.0005', 'format=geojson', out)
    # simplification can drop very small municipalities entirely: put their original shape back
    g = json.load(open(out)); r = {f['properties']['id']: f for f in json.load(open(raw))['features']}
    have = {f['properties']['id'] for f in g['features'] if f.get('geometry')}
    fixed = [r[i] for i in r if i not in have]
    if fixed:
        g['features'] = [f for f in g['features'] if f.get('geometry')] + fixed
        json.dump(g, open(out, 'w'))
        print(uf, 'restored original geometry for', [f['properties']['name'] for f in fixed], flush=True)
    return out


def sources(uf, d):
    st = json.load(open(os.path.join(d, 'status.json')))
    p = os.path.join(d, 'sources.json')
    json.dump([
        {'label': f'TSE · Boletim de Urna · {uf} · 2º turno · {os.path.basename(st["bu_url"])}', 'url': st['bu_url'], 'sha512': st['bu_sha512'],
         'note': 'SHA-512 publicado pelo TSE (arquivo .sha512) e conferido.'},
        {'label': f'TSE · Arquivos transmitidos para totalização (BU, RDV, log, assinaturas) · {uf} · 2º turno', 'url': st['arq_url'],
         'note': f'O TSE não publica SHA-512 para este arquivo. Tamanho {st.get("arq_size")} bytes; ETag {st.get("arq_etag")}; '
                 f'Last-Modified {st.get("arq_modified")}. Logs lidos diretamente do servidor do TSE, urna por urna.'},
    ], open(p, 'w'), ensure_ascii=False)
    return p


STATE_META = {'11': ('RO', 'Rondônia', 'N'), '12': ('AC', 'Acre', 'N'), '13': ('AM', 'Amazonas', 'N'), '14': ('RR', 'Roraima', 'N'),
    '15': ('PA', 'Pará', 'N'), '16': ('AP', 'Amapá', 'N'), '17': ('TO', 'Tocantins', 'N'), '21': ('MA', 'Maranhão', 'NE'),
    '22': ('PI', 'Piauí', 'NE'), '23': ('CE', 'Ceará', 'NE'), '24': ('RN', 'Rio Grande do Norte', 'NE'), '25': ('PB', 'Paraíba', 'NE'),
    '26': ('PE', 'Pernambuco', 'NE'), '27': ('AL', 'Alagoas', 'NE'), '28': ('SE', 'Sergipe', 'NE'), '29': ('BA', 'Bahia', 'NE'),
    '31': ('MG', 'Minas Gerais', 'SE'), '32': ('ES', 'Espírito Santo', 'SE'), '33': ('RJ', 'Rio de Janeiro', 'SE'), '35': ('SP', 'São Paulo', 'SE'),
    '41': ('PR', 'Paraná', 'S'), '42': ('SC', 'Santa Catarina', 'S'), '43': ('RS', 'Rio Grande do Sul', 'S'),
    '50': ('MS', 'Mato Grosso do Sul', 'CO'), '51': ('MT', 'Mato Grosso', 'CO'), '52': ('GO', 'Goiás', 'CO'), '53': ('DF', 'Distrito Federal', 'CO')}
sg_out = os.path.join(SITE, 'geo', 'br_states.json')
if not os.path.exists(sg_out):
    # state outlines: dissolve all municipalities by state code (mapshaper), then attach names/regions
    allm = os.path.join(W, 'geojs-100-mun.json'); raw = os.path.join(W, 'br_states_raw.json')
    if not os.path.exists(raw):
        if not os.path.exists(allm): sh('curl', '-sSf', '-m', '600', '-o', allm, GEO.format(code='100'))
        sh('node', MAPSHAPER, allm, '-each', 'uf=id.slice(0,2)', '-dissolve2', 'uf', '-simplify', '2%', 'keep-shapes', '-clean',
           '-o', 'precision=0.001', 'format=geojson', raw)
    sg = json.load(open(raw))
    for f in sg['features']:
        s, n, r = STATE_META[f['properties']['uf']]; f['properties'] = {'uf': s, 'code': f['properties']['uf'], 'name': n, 'region': r}
    os.makedirs(os.path.dirname(sg_out), exist_ok=True); json.dump(sg, open(sg_out, 'w'), separators=(',', ':'), ensure_ascii=False)

for d in sorted(glob.glob(os.path.join(W, 'states', '*'))):
    uf = os.path.basename(d)
    if ONLY and uf not in ONLY: continue
    st = json.load(open(os.path.join(d, 'status.json'))) if os.path.exists(os.path.join(d, 'status.json')) else {}
    bweb = glob.glob(os.path.join(d, 'bu', 'bweb_2t_*.csv'))[0] if glob.glob(os.path.join(d, 'bu', 'bweb_2t_*.csv')) else None
    if uf == 'ZZ' and bweb:   # votes abroad: BU only
        args = [sys.executable, '-I', os.path.join(HERE, 'build_site_data.py'), '--uf', 'ZZ', '--abroad', '--bweb', bweb, '--out', SITE,
                '--sources', os.path.join(d, 'sources.json')]
        print(uf, sh(*args).strip(), flush=True); continue
    if not st.get('logs'): print(uf, 'logs not ready, skipped', flush=True); continue
    args = [sys.executable, '-I', os.path.join(HERE, 'build_site_data.py'), '--uf', uf, '--bweb', bweb, '--logs', os.path.join(d, 'logs'),
            '--geo-mun', prep_geo(uf, d), '--out', SITE, '--sources', sources(uf, d)]
    notes = os.path.join(HERE, 'sources', f'{uf}_2t_notes.json')
    if os.path.exists(notes): args += ['--notes', notes]
    try:
        print(uf, sh(*args).strip(), flush=True)
    except subprocess.CalledProcessError as e:
        print(uf, 'FAILED', e.stderr[-1500:], flush=True)
print(sh(sys.executable, '-I', os.path.join(HERE, 'finalize_manifest.py'), SITE).strip())
