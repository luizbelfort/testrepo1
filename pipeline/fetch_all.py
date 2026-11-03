"""Driver: for each state, download + verify the BU CSV, index the urna-files zip, parse every urna log.
Resumable: finished steps/urnas are skipped. usage: python fetch_all.py <workdir> <UF,UF,...> [threads]"""
import hashlib, json, os, subprocess, sys, time, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
W, UFS = sys.argv[1], sys.argv[2].split(',')
THREADS = sys.argv[3] if len(sys.argv) > 3 else '4'   # processes (each runs 8 download threads)
BU_PKG = 'https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna'
ARQ = 'https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_2t_{uf}.zip'

def sh(*a): return subprocess.run(list(a), check=True, capture_output=True).stdout
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)

cache = os.path.join(W, 'pkg_bu.json')   # catalogue of BU files; the saved copy is used if the portal API is down
try:
    raw = sh('curl', '-sSf', '--retry', '6', '--retry-all-errors', '-m', '120', BU_PKG); open(cache, 'wb').write(raw)
except subprocess.CalledProcessError:
    log('portal API unavailable, using saved catalogue'); raw = open(cache, 'rb').read()
pkg = json.loads(raw)['result']['resources']
bu_url = {r['url'].split('_')[2]: r['url'] for r in pkg if '_2t_' in r['url'] and r['url'].endswith('.zip')}
for uf in UFS:
    d = os.path.join(W, 'states', uf); os.makedirs(d, exist_ok=True)
    st = os.path.join(d, 'status.json'); status = json.load(open(st)) if os.path.exists(st) else {}
    try:
        if not status.get('bu'):
            url = bu_url[uf]; zp = os.path.join(d, os.path.basename(url))
            sh('curl', '-sSf', '--retry', '6', '--retry-all-errors', '-m', '1800', '-o', zp, url)
            exp = sh('curl', '-sSf', '--retry', '6', '--retry-all-errors', '-m', '120', url + '.sha512').decode().split()[0]
            got = hashlib.sha512(open(zp, 'rb').read()).hexdigest()
            if got != exp: raise SystemExit(f'{uf}: SHA-512 mismatch for {url}')
            zipfile.ZipFile(zp).extractall(os.path.join(d, 'bu'))
            hdr = sh('curl', '-sSI', '--retry', '6', '--retry-all-errors', '-m', '60', ARQ.format(uf=uf)).decode('latin1')
            h = {l.split(':', 1)[0].lower(): l.split(':', 1)[1].strip() for l in hdr.splitlines() if ':' in l}
            status.update(bu=True, bu_url=url, bu_sha512=got, arq_url=ARQ.format(uf=uf), arq_size=h.get('content-length'),
                          arq_etag=h.get('etag'), arq_modified=h.get('last-modified'))
            json.dump(status, open(st, 'w'), indent=1); log(uf, 'BU ok', got[:16])
        idx = os.path.join(d, 'index.pkl')
        if not os.path.exists(idx):
            log(uf, sh(sys.executable, '-I', os.path.join(HERE, 'index_zip.py'), ARQ.format(uf=uf), idx).decode().strip())
        if not status.get('logs'):
            t0 = time.time()
            out = sh(sys.executable, '-I', os.path.join(HERE, 'run_full.py'), W, ARQ.format(uf=uf), idx, os.path.join(d, 'logs'), THREADS).decode()
            log(uf, out.strip().splitlines()[-1], f'{time.time() - t0:.0f}s')
            if json.load(open(os.path.join(d, 'logs', '_errors.json'))):
                log(uf, 'has errors; will retry on next run'); continue
            status['logs'] = True; json.dump(status, open(st, 'w'), indent=1)
    except Exception as e:
        log(uf, 'FAILED', repr(e)[:300])
log('done')
