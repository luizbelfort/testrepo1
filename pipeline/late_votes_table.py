"""Per-urna table of the votes cast near and after the regular closing time (17:00, Brasília), for every urna in
Brazil. Inputs: the site's state files (BU totals, time zone per municipality) and the parsed urna logs.

For each urna and each cutoff C, counts the votes computed strictly after C, split by how the voter was enabled:
  bio    = fingerprint recognised
  failed = fingerprint on file but not recognised; released by a mesário ("não habilitado por biometria")
  noask  = the urna did not ask for a fingerprint
"Sem biometria" in the analysis = failed + noask.

usage: python late_votes_table.py <workdir> <site dir> <out.parquet>
"""
import glob, gzip, json, os, re, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq

CUTS = {'c1700': 17 * 3600, 'c1701': 17 * 3600 + 60, 'c1705': 17 * 3600 + 300, 'c1710': 17 * 3600 + 600,
        'c1730': 17 * 3600 + 1800, 'c1800': 18 * 3600, 'c1830': 18 * 3600 + 1800, 'c1900': 19 * 3600}
H16 = 16 * 3600
COLS = ['fname', 't_vote', 'manual', 'hab_type', 't_hab', 't_fp_first', 't_manual', 't_mesario', 'recovered', 'releaser']
KEY = re.compile(r'(\d{13})-log\.jez$')


def state_logs(logdir, cols=None):
    """Yield DataFrames of parsed voters, one batch at a time; reprocessed urnas: newest batch only."""
    batches = sorted(glob.glob(os.path.join(logdir, 'batch_*.parquet')), key=os.path.getmtime)
    owner = {}
    for p in batches:
        for l in open(p.replace('batch_', 'meta_').replace('.parquet', '.jsonl')):
            owner[json.loads(l)['fname']] = p
    for p in batches:
        t = pq.read_table(p, columns=[c for c in (cols or COLS) if c in pq.read_schema(p).names]).to_pandas()
        yield t[t.fname.map(owner).values == p]
    olds = [p for p in glob.glob(os.path.join(logdir, '*-log.jez.parquet')) if os.path.basename(p)[:-8] not in owner]
    buf = []
    for i, p in enumerate(olds):
        df = pq.read_table(p).to_pandas(); df['fname'] = os.path.basename(p)[:-8]; buf.append(df)
        if len(buf) == 300 or i == len(olds) - 1:
            yield pd.concat(buf, ignore_index=True); buf = []


def main():
    W, SITE, OUT = sys.argv[1:4]
    rows = []
    minute_hist = []   # national per-minute histogram after 16:00 by kind and urna group
    for p in sorted(glob.glob(os.path.join(SITE, 'data', '*.json.gz'))):
        uf = os.path.basename(p)[:2]
        d = json.load(gzip.open(p))
        if d.get('abroad'): continue
        u, m = d['urnas'], d['munis']
        nU = len(u['m'])
        key = {f"{int(m['tse'][u['m'][k]]):05d}{u['z'][k]:04d}{u['s'][k]:04d}": k for k in range(nU)}
        tz = np.array([(m['tz'][u['m'][k]] or 0) * 3600 for k in range(nU)])
        comp = np.array(u['comp'])
        acc = {f'{c}_{kind}': np.zeros(nU, int) for c in CUTS for kind in ('all', 'failed', 'noask', 'fast', 'unreg')}
        acc |= {f'h16_{kind}': np.zeros(nU, int) for kind in ('all', 'failed', 'noask', 'fast')}
        acc |= {f'day_{kind}': np.zeros(nU, int) for kind in ('all', 'failed', 'noask', 'fast', 'unreg')}
        first = np.full(nU, 10 ** 9); last = np.full(nU, -1); nlog = np.zeros(nU, int); has_log = np.zeros(nU, bool)
        recdrop = np.zeros(nU, int)
        for V in state_logs(os.path.join(W, 'states', uf, 'logs')):
            V = V[V.t_vote >= 0]
            ui = V.fname.map(lambda f: key.get(KEY.search(f).group(1), -1)).values
            V = V[ui >= 0]; ui = ui[ui >= 0]
            if not len(V): continue
            has_log[np.unique(ui)] = True
            rec = V.recovered.fillna(False).astype(bool).values if 'recovered' in V else np.zeros(len(V), bool)
            n_all = np.bincount(ui, minlength=nU); n_rec = np.bincount(ui[rec], minlength=nU)
            drop_u = (n_rec > 0) & (n_all != comp) & (n_all - n_rec == comp)        # same reconciliation as the builder
            keep = ~(rec & drop_u[ui])
            recdrop += np.bincount(ui[~keep], minlength=nU)
            V = V[keep]; ui = ui[keep]
            off = tz[ui]
            tv = V.t_vote.values + off
            th = np.where(V.t_hab.values >= 0, V.t_hab.values + off, -1)
            failed = V.manual.values.astype(bool)
            bio = (V.hab_type.values == 'biométrica') & ~failed
            noask = ~failed & ~bio
            tf, tm, tr = V.t_fp_first.values, V.t_manual.values, V.t_mesario.values
            fast = failed & (tf >= 0) & (tm - tf <= 30) & (tr >= 0) & (tr - tm <= 10) & (th >= 0) & (tv - th <= 5)
            unreg = failed & np.isin(V.releaser.values if 'releaser' in V else np.array([None] * len(V)), ['unregistered_new', 'unregistered_repeat'])
            nlog += np.bincount(ui, minlength=nU)
            np.maximum.at(last, ui, tv)
            np.minimum.at(first, ui, tv)
            masks = {'all': np.ones(len(V), bool), 'failed': failed, 'noask': noask, 'fast': fast, 'unreg': unreg}
            for c, t in CUTS.items():
                after = tv > t
                for kind, mk in masks.items(): acc[f'{c}_{kind}'] += np.bincount(ui[after & mk], minlength=nU)
            h = (tv > H16) & (tv <= CUTS['c1700'])
            for kind in ('all', 'failed', 'noask', 'fast'): acc[f'h16_{kind}'] += np.bincount(ui[h & masks[kind]], minlength=nU)
            for kind, mk in masks.items(): acc[f'day_{kind}'] += np.bincount(ui[mk], minlength=nU)
            sel = tv > H16
            if sel.any():
                kind = np.where(failed, 'failed', np.where(noask, 'noask', 'bio'))
                minute_hist.append(pd.DataFrame({'uf': uf, 'ui': ui[sel], 'minute': tv[sel] // 60, 'kind': kind[sel]})
                                   .groupby(['uf', 'ui', 'minute', 'kind']).size().rename('n').reset_index())
        first = np.where(first == 10 ** 9, -1, first)
        df = pd.DataFrame({'uf': uf, 'ui': np.arange(nU), 'm': u['m'], 'ibge': [m['ibge'][x] for x in u['m']],
                           'muni': [m['name'][x] for x in u['m']], 'zona': u['z'], 'secao': u['s'], 'local': u['loc'],
                           'aptos': u['aptos'], 'comp': comp, 'lula': u['lula'], 'flavio': u['flavio'], 'branco': u['branco'],
                           'nulo': u['nulo'], 'bu_failed': u['manual'], 'open': u['open'], 'close': u['close'], 'recv': u['recv'],
                           'model': [d['models'][x] if x >= 0 else '?' for x in u['model']], 'tz_h': tz // 3600,
                           'has_log': has_log, 'n_log': nlog, 'rec_dropped': recdrop, 'first_vote': first, 'last_vote': last, **acc})
        rows.append(df)
        print(uf, nU, 'urnas;', int(df.c1700_all.sum()), 'votes after 17:00;', int(df.c1710_all.sum()), 'after 17:10', flush=True)
    T = pd.concat(rows, ignore_index=True)
    T.to_parquet(OUT)
    pd.concat(minute_hist, ignore_index=True).to_parquet(OUT.replace('.parquet', '_minutes.parquet'))
    print('total urnas', len(T), '| votes after 17:00:', int(T.c1700_all.sum()), '| log votes', int(T.n_log.sum()), '| BU comp', int(T.comp.sum()))


if __name__ == '__main__':
    main()
