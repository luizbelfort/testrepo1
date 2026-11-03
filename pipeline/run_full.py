"""Process every urna log of one state/round: parse each log, keep compact per-voter rows (parquet per urna)."""
import sys, os, json, pickle, threading, time, glob
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from httpzip import HTTPFile
from parse_log import parse

S, URL, INDEX, OUT = sys.argv[1:5]
THREADS = int(sys.argv[5]) if len(sys.argv) > 5 else 16
os.makedirs(OUT, exist_ok=True)
idx = {n: (o, c) for n, o, c, u in pickle.load(open(INDEX, 'rb')) if n.endswith('-log.jez')}
KEEP = ['t_id', 't_fp_first', 'fp_tries', 'hab_type', 'manual', 't_manual', 'data_fail', 't_mes_req',
        'releaser', 't_mesario', 't_hab', 't_vote', 'recovered', 'cancelled']
def secs(x):
    if not isinstance(x, str): return -1
    h, m, s = x.split(':'); return int(h) * 3600 + int(m) * 60 + int(s)
f_local = threading.local()
def worker(fname, idx_entry=None, raw=None):
    if raw is None:
        if not hasattr(f_local, 'f'): f_local.f = HTTPFile(URL)
        raw = f_local.f.get_member(*(idx_entry or idx[fname]))
    voters, meta = parse(raw)
    rows = {k: [v[k] for v in voters] for k in KEEP}
    for c in [c for c in KEEP if c.startswith('t_')]: rows[c] = [secs(x) for x in rows[c]]
    meta = {k: meta[k] for k in ['model', 'open', 'close', 'files', 'contingency', 'restarts', 'urna_ids']} | {'n_mesarios': len(meta['mesarios_sec']), 'fname': fname}
    return rows, meta


def done_names():
    names = set()
    for p in glob.glob(f'{OUT}/meta_*.jsonl'):
        names |= {json.loads(l)['fname'] for l in open(p)}
    names |= {os.path.basename(p)[:-8] for p in glob.glob(f'{OUT}/*-log.jez.parquet')}   # older one-file-per-urna format
    return names


def fetch_many(names, tmp):
    """Fetch many zip members with ONE curl process (connection reuse, 8 parallel transfers).
    Each range covers the local header + data + slack for the extra field."""
    import struct, subprocess, tempfile, zlib
    cfg = []
    for i, (fn, (off, csz)) in enumerate(names):
        cfg.append((("next\n") if i else "") + f'url = "{URL}"\nrange = {off}-{off + 30 + len(fn) + csz + 1024}\noutput = "{tmp}/{i}"\n')
    cp = f'{tmp}/curl.cfg'; open(cp, 'w').write(''.join(cfg))
    subprocess.run(['curl', '-sS', '--retry', '5', '--retry-all-errors', '-m', '600', '--parallel', '--parallel-max', '8', '-K', cp], capture_output=True)
    out = {}
    for i, (fn, (off, csz)) in enumerate(names):
        try:
            blob = open(f'{tmp}/{i}', 'rb').read()
            sig, ver, flag, meth, _, _, crc, _, _, nlen, xlen = struct.unpack('<IHHHHHIIIHH', blob[:30])
            assert sig == 0x04034b50
            data = blob[30 + nlen + xlen: 30 + nlen + xlen + csz]
            assert len(data) == csz
            out[fn] = data if meth == 0 else zlib.decompress(data, -15)
        except Exception as e:
            out[fn] = e
    return out


def batch(names):
    import tempfile
    res = []
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        blobs = fetch_many(names, tmp)
    for attempt in range(2):   # re-batch transient failures before falling back to one-by-one requests
        failed = [(fn, ent) for fn, ent in names if not isinstance(blobs.get(fn), (bytes, bytearray))]
        if not failed: break
        with tempfile.TemporaryDirectory(dir=OUT) as tmp:
            blobs.update(fetch_many(failed, tmp))
    for fn, ent in names:
        b = blobs.get(fn)
        if not isinstance(b, (bytes, bytearray)):   # retry this one alone through the range reader
            try:
                if not hasattr(f_local, 'f'): f_local.f = HTTPFile(URL)
                b = f_local.f.get_member(*ent)
            except Exception as e:
                res.append((fn, None, repr(e)[:200])); continue
        try: res.append((fn, worker(fn, raw=b), None))
        except Exception as e: res.append((fn, None, repr(e)[:200]))
    ok = [(fn, r) for fn, r, e in res if r]
    if ok:
        import pyarrow as pa, pyarrow.parquet as pq
        cols = {k: [] for k in KEEP}; cols['fname'] = []
        for fn, (rows, meta) in ok:
            for k in KEEP: cols[k] += rows[k]
            cols['fname'] += [fn] * len(rows['t_vote'])
        tag = ok[0][0].replace('-log.jez', '')
        tbl = pa.table({**{k: cols[k] for k in KEEP}, 'fname': cols['fname']})
        pq.write_table(tbl, f'{OUT}/batch_{tag}.parquet.tmp'); os.replace(f'{OUT}/batch_{tag}.parquet.tmp', f'{OUT}/batch_{tag}.parquet')
        with open(f'{OUT}/meta_{tag}.jsonl.tmp', 'w') as fh:
            for fn, (rows, meta) in ok: fh.write(json.dumps(meta) + '\n')
        os.replace(f'{OUT}/meta_{tag}.jsonl.tmp', f'{OUT}/meta_{tag}.jsonl')
    return [(fn, None, e) for fn, r, e in res]


if __name__ == '__main__':
    have = done_names()
    todo = [(fn, idx[fn]) for fn in idx if fn not in have]
    chunks = [todo[i:i + 200] for i in range(0, len(todo), 200)]
    t0 = time.time(); done = 0; errs = []; last = 0
    with ProcessPoolExecutor(THREADS) as ex:
        for res in ex.map(batch, chunks):
            for fn, ok, err in res:
                done += 1
                if err: errs.append((fn, err))
            if done - last >= 5000: last = done; print(f'{done}/{len(todo)} {time.time()-t0:.0f}s errors={len(errs)}', flush=True)
    json.dump(errs, open(f'{OUT}/_errors.json', 'w'))
    print('finished', done, 'errors', len(errs), f'{time.time()-t0:.0f}s', flush=True)
