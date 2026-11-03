"""Process every urna log of one state/round: parse each log, keep compact per-voter rows (parquet per urna)."""
import sys, os, json, pickle, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from httpzip import HTTPFile
from parse_log import parse

S, URL, INDEX, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
idx = {n: (o, c) for n, o, c, u in pickle.load(open(INDEX, 'rb')) if n.endswith('-log.jez')}
KEEP = ['t_id', 't_fp_first', 'fp_tries', 'hab_type', 'manual', 't_manual', 'data_fail', 't_mes_req',
        'releaser', 't_mesario', 't_hab', 't_vote', 'cancelled']
def secs(x):
    if not isinstance(x, str): return -1
    h, m, s = x.split(':'); return int(h) * 3600 + int(m) * 60 + int(s)
f_local = threading.local()
def worker(fname):
    p = f'{OUT}/{fname}.parquet'
    if os.path.exists(p): return 'skip'
    if not hasattr(f_local, 'f'): f_local.f = HTTPFile(URL)
    raw = f_local.f.get_member(*idx[fname])
    voters, meta = parse(raw)
    df = pd.DataFrame([{k: v[k] for k in KEEP} for v in voters], columns=KEEP)
    for c in [c for c in KEEP if c.startswith('t_')]: df[c] = df[c].map(secs).astype('int32')
    df['fp_tries'] = df.fp_tries.astype('int8'); df['data_fail'] = df.data_fail.astype('int8')
    meta = {k: meta[k] for k in ['model', 'open', 'close', 'files']} | {'n_mesarios': len(meta['mesarios_sec'])}
    df.attrs = {}
    import pyarrow as pa, pyarrow.parquet as pq
    tbl = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata({'meta': json.dumps(meta)})
    pq.write_table(tbl, p + '.tmp'); os.replace(p + '.tmp', p)
    return 'ok'
t0 = time.time(); done = 0; errs = []
with ThreadPoolExecutor(16) as ex:
    futs = {ex.submit(worker, fn): fn for fn in idx}
    for fu in as_completed(futs):
        try: fu.result()
        except Exception as e: errs.append((futs[fu], repr(e)[:200]))
        done += 1
        if done % 1000 == 0: print(f'{done}/{len(futs)} {time.time()-t0:.0f}s errors={len(errs)}', flush=True)
json.dump(errs, open(f'{OUT}/_errors.json', 'w'))
print('finished', done, 'errors', len(errs), f'{time.time()-t0:.0f}s', flush=True)
