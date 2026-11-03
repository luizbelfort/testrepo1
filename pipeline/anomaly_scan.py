"""National anomaly scan over the parsed urna logs (one row per urna). Every metric is a count or a standard test;
flags are thresholds on those, documented in the output. A flag is a pattern to check, not proof of anything.

Per urna:
  failed / noask / bio voters; failed-read rate and its binomial tail p-value against the municipality's rate;
  longest run of consecutive failed-read releases and its probability under random order (run-length formula);
  fast votes (failed read, fingerprint phase <=30 s, release <=10 s, vote <=5 s) and very fast votes (vote <=3 s);
  releases by unregistered fingerprints; identity-data failures; voters released who never voted;
  turnout and its z-score within the municipality.

usage: python anomaly_scan.py <workdir> <site dir> <out.parquet>
"""
import glob, gzip, json, math, os, re, sys
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from late_votes_table import state_logs, KEY

COLS_NEEDED = ['fname', 't_vote', 'manual', 'hab_type', 't_hab', 't_fp_first', 't_manual', 't_mesario', 'recovered', 'releaser', 'data_fail', 'cancelled']


def longest_run(mask, ui, nU):
    """Longest run of True per urna, rows ordered by voter within each urna (vectorised)."""
    out = np.zeros(nU, int)
    if not len(mask): return out
    mask = np.asarray(mask, bool); idx = np.arange(len(mask))
    brk = np.r_[True, ui[1:] != ui[:-1]]
    reset = np.where(~mask, idx, np.where(brk, idx - 1, -1))
    last = np.maximum.accumulate(reset)
    r = np.where(mask, idx - last, 0)
    np.maximum.at(out, ui, r)
    return out


def p_run_at_least(L, n, p):
    """P(longest run of successes >= L) in n Bernoulli(p) trials, Poisson approximation (accurate for small p^L)."""
    if L <= 0 or n <= 0: return 1.0
    if p <= 0: return 0.0
    if p >= 1: return 1.0
    lam = (n - L + 1) * (1 - p) * p ** L + p ** L
    return float(1 - math.exp(-max(lam, 0)))


def main():
    W, SITE, OUT = sys.argv[1:4]
    rows = []
    for p in sorted(glob.glob(os.path.join(SITE, 'data', '*.json.gz'))):
        if not re.fullmatch(r'[A-Z]{2}\.json\.gz', os.path.basename(p)): continue
        uf = os.path.basename(p)[:2]
        d = json.load(gzip.open(p))
        if d.get('abroad'): continue
        u, m = d['urnas'], d['munis']; nU = len(u['m'])
        key = {f"{int(m['tse'][u['m'][k]]):05d}{u['z'][k]:04d}{u['s'][k]:04d}": k for k in range(nU)}
        comp = np.array(u['comp'])
        acc = {k: np.zeros(nU, int) for k in ('n', 'failed', 'noask', 'bio', 'fast', 'vfast_failed', 'vfast_bio', 'unreg', 'data_fail', 'hab_no_vote', 'run_failed')}
        for V in state_logs(os.path.join(W, 'states', uf, 'logs'), COLS_NEEDED):
            for c in ('data_fail', 'releaser', 'recovered'):
                if c not in V: V[c] = 0 if c == 'data_fail' else None
            ui_all = V.fname.map(lambda f: key.get(KEY.search(f).group(1), -1)).values
            V = V[ui_all >= 0].reset_index(drop=True); ui_all = ui_all[ui_all >= 0]
            if not len(V): continue
            # released (habilitado) but never voted
            hv = (V.t_vote.values < 0) & (V.t_hab.values >= 0)
            acc['hab_no_vote'] += np.bincount(ui_all[hv], minlength=nU)
            sel = V.t_vote.values >= 0
            V = V[sel].reset_index(drop=True); ui = ui_all[sel]
            rec = V.recovered.fillna(False).astype(bool).values if 'recovered' in V else np.zeros(len(V), bool)
            n_all = np.bincount(ui, minlength=nU); n_rec = np.bincount(ui[rec], minlength=nU)
            drop_u = (n_rec > 0) & (n_all != comp) & (n_all - n_rec == comp)
            keep = ~(rec & drop_u[ui]); V = V[keep].reset_index(drop=True); ui = ui[keep]
            failed = V.manual.values.astype(bool); bio = (V.hab_type.values == 'biométrica') & ~failed; noask = ~failed & ~bio
            tv, th, tf, tm, tr = (V[c].values for c in ('t_vote', 't_hab', 't_fp_first', 't_manual', 't_mesario'))
            vs = np.where(th >= 0, tv - th, 10 ** 6)
            fast = failed & (tf >= 0) & (tm - tf <= 30) & (tr >= 0) & (tr - tm <= 10) & (vs <= 5)
            unreg = failed & np.isin(V.releaser.values, ['unregistered_new', 'unregistered_repeat'])
            for k, mk in (('n', np.ones(len(V), bool)), ('failed', failed), ('noask', noask), ('bio', bio), ('fast', fast),
                          ('vfast_failed', failed & (vs <= 3)), ('vfast_bio', bio & (vs <= 3)), ('unreg', unreg)):
                acc[k] += np.bincount(ui[mk], minlength=nU)
            acc['data_fail'] += np.bincount(ui, weights=V.data_fail.fillna(0).values, minlength=nU).astype(int)
            acc['run_failed'] = np.maximum(acc['run_failed'], longest_run(failed, ui, nU))
        df = pd.DataFrame({'uf': uf, 'ui': np.arange(nU), 'ibge': [m['ibge'][x] for x in u['m']], 'muni': [m['name'][x] for x in u['m']],
                           'zona': u['z'], 'secao': u['s'], 'local': u['loc'], 'aptos': u['aptos'], 'comp': comp,
                           'lula': u['lula'], 'flavio': u['flavio'], 'bu_failed': u['manual'], 'close': u['close'],
                           'model': [d['models'][x] if x >= 0 else '?' for x in u['model']], **acc})
        rows.append(df)
        print(uf, nU, 'urnas', flush=True)
    T = pd.concat(rows, ignore_index=True)
    T = T[T.n > 0].copy()
    # municipality reference rates and tests
    g = T.groupby(['uf', 'ibge'])
    T['mun_failed_rate'] = g.failed.transform('sum') / g.n.transform('sum')
    T['failed_rate'] = T.failed / T.n
    T['p_failed_high'] = stats.binom.sf(T.failed - 1, T.n, T.mun_failed_rate.clip(1e-6, 1 - 1e-6))
    T['p_run'] = [p_run_at_least(L, n, q) for L, n, q in zip(T.run_failed, T.n, T.failed_rate)]
    T['turnout'] = T.comp / T.aptos.clip(lower=1)
    gm = T.groupby(['uf', 'ibge']).turnout
    T['turnout_z'] = (T.turnout - gm.transform('mean')) / gm.transform('std').replace(0, np.nan)
    T['lula_share'] = T.lula / (T.lula + T.flavio).clip(lower=1)
    T['unreg_share'] = T.unreg / T.failed.clip(lower=1)
    T.to_parquet(OUT)
    print('scanned', len(T), 'urnas', flush=True)


if __name__ == '__main__':
    main()
