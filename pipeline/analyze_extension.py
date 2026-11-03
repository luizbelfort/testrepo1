"""Did keeping urnas open after 17:00 favour a candidate? Analysis of the per-urna late-vote table.

The urna log records WHEN each vote was cast, never FOR WHOM; the RDV records for whom, in shuffled order.
So the candidate of a late vote is unknowable. What can be stated with certainty:
  * how many votes were cast after each cutoff, where, and how voters were enabled;
  * exact bounds for a "hard stop": removing every vote cast after the cutoff can change a result by at most
    min(late votes, candidate's votes) per urna, in either direction.
Model-based numbers (lean of the urnas, polling-place comparisons, regression) are labelled as estimates.

usage: python analyze_extension.py <late_votes.parquet> <site dir> <report.md>
"""
import gzip, json, math, os, sys
import numpy as np, pandas as pd

CUTS = [('c1700', '17:00', 17 * 3600), ('c1701', '17:01', 17 * 3600 + 60), ('c1705', '17:05', 17 * 3600 + 300),
        ('c1710', '17:10', 17 * 3600 + 600), ('c1730', '17:30', 17 * 3600 + 1800), ('c1800', '18:00', 18 * 3600),
        ('c1830', '18:30', 18 * 3600 + 1800), ('c1900', '19:00', 19 * 3600)]
REGION = {'RO': 'N', 'AC': 'N', 'AM': 'N', 'RR': 'N', 'PA': 'N', 'AP': 'N', 'TO': 'N', 'MA': 'NE', 'PI': 'NE', 'CE': 'NE', 'RN': 'NE',
          'PB': 'NE', 'PE': 'NE', 'AL': 'NE', 'SE': 'NE', 'BA': 'NE', 'MG': 'SE', 'ES': 'SE', 'RJ': 'SE', 'SP': 'SE', 'PR': 'S', 'SC': 'S',
          'RS': 'S', 'MS': 'CO', 'MT': 'CO', 'GO': 'CO', 'DF': 'CO'}
REGION_NAME = {'N': 'Norte', 'NE': 'Nordeste', 'CO': 'Centro-Oeste', 'SE': 'Sudeste', 'S': 'Sul'}
GROUPS = [('A', 'encerrou até 17:01', -1, 17 * 3600 + 60), ('B', 'encerrou 17:01–17:10 (filas normais)', 17 * 3600 + 60, 17 * 3600 + 600),
          ('C', 'encerrou 17:10–18:55', 17 * 3600 + 600, 18 * 3600 + 55 * 60), ('D', 'encerrou a partir de 18:55 ("mais duas horas")', 18 * 3600 + 55 * 60, 10 ** 9)]


def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if hasattr(o, 'item'): o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)): return None
    return o


def br(n, d=0):
    if n is None or (isinstance(n, float) and math.isnan(n)): return '—'
    s = f'{n:,.{d}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(x, d=1):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) else br(100 * x, d) + '%'


def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def bounds(df, cut, extra_lula=0, extra_flavio=0):
    """Hard-stop bounds for removing every vote cast after `cut` (votes without a log time count as possibly late)."""
    k = df[f'{cut}_all'].values + df.unknown.values
    L, F = df.lula.values, df.flavio.values
    a = np.minimum(k, L).sum(); b = np.minimum(k, F).sum()          # max Lula / Flávio votes removable
    Lt, Ft = L.sum() + extra_lula, F.sum() + extra_flavio
    M = Lt - Ft
    return {'late_votes': int(k.sum()), 'urnas_with_late': int((k > 0).sum()), 'lula': int(Lt), 'flavio': int(Ft), 'margin': int(M),
            'max_lula_removed': int(a), 'max_flavio_removed': int(b),
            'margin_min': int(M - a), 'margin_max': int(M + b),
            'lula_share': Lt / (Lt + Ft), 'lula_share_min': (Lt - a) / (Lt - a + Ft), 'lula_share_max': Lt / (Lt + Ft - b),
            'winner': 'lula' if M > 0 else 'flavio' if M < 0 else 'empate',
            # a hard stop can only matter where votes were cast after the cutoff
            'winner_can_change': bool(k.sum() > 0 and ((M > 0 and M - a < 0) or (M < 0 and M + b > 0) or (M == 0 and (a > 0 or b > 0)))),
            'tie_possible': bool(k.sum() > 0 and ((M > 0 and M - a <= 0) or (M < 0 and M + b >= 0)))}


def place_regression(df, cut):
    """Within each polling place: Lula share of valid votes vs fraction of the urna's votes cast after `cut`.
    Slope = (Lula share among late voters) - (Lula share among the place's other voters). Cluster-robust SE."""
    d = df[(df.has_log) & (df.lula + df.flavio > 0)].copy()
    d['s'] = d.lula / (d.lula + d.flavio); d['f'] = d[f'{cut}_all'] / d.comp.clip(lower=1); d['w'] = d.lula + d.flavio
    d['place'] = d.uf + '|' + d.zona.astype(str) + '|' + d.local.astype(str)
    g = d.groupby('place')
    d['n'] = g.f.transform('size'); d = d[d.n > 1]
    wm = lambda col: (d[col] * d.w).groupby(d.place).transform('sum') / d.w.groupby(d.place).transform('sum')
    d['x'] = d.f - wm('f'); d['y'] = d.s - wm('s')
    sxx = (d.w * d.x * d.x).sum()
    if sxx <= 0: return None
    beta = (d.w * d.x * d.y).sum() / sxx
    d['e'] = d.y - beta * d.x
    meat = ((d.w * d.x * d.e).groupby(d.place).sum() ** 2).sum()
    se = math.sqrt(meat) / sxx
    base = (d.s * d.w).sum() / d.w.sum()
    # baseline of the places that identify beta (leverage-weighted): the implied Lula share among late voters
    lev = (d.w * d.x * d.x).groupby(d.place).sum(); qpl = wm('s').groupby(d.place).first()
    qstar = float((lev * qpl.loc[lev.index]).sum() / lev.sum())
    res = {'beta': beta, 'se': se, 'ci': [beta - 1.96 * se, beta + 1.96 * se], 'baseline_lula_share': base,
           'baseline_identifying_places': qstar, 'implied_late_lula_share': qstar + beta,
           'implied_late_ci': [qstar + beta - 1.96 * se, qstar + beta + 1.96 * se],
           'z_vs_80pct': (qstar + beta - 0.80) / se, 'z_vs_65pct': (qstar + beta - 0.65) / se,
           'places': int(d.place.nunique()), 'urnas': int(len(d)), 'late_votes_used': int(d[f'{cut}_all'].sum())}
    # robustness: unweighted; placebo (late fractions shuffled within place)
    d['one'] = 1.0
    def fe_beta(dd, wcol):
        m = lambda col: (dd[col] * dd[wcol]).groupby(dd.place).transform('sum') / dd[wcol].groupby(dd.place).transform('sum')
        x = dd.f - m('f'); y = dd.s - m('s')
        return float((dd[wcol] * x * y).sum() / (dd[wcol] * x * x).sum())
    res['beta_unweighted'] = fe_beta(d, 'one')
    rng = np.random.default_rng(1); pb = []
    for _ in range(20):
        dp = d.copy(); dp['f'] = dp.groupby('place').f.transform(lambda v: rng.permutation(v.values)); pb.append(fe_beta(dp, 'w'))
    res['placebo_mean'] = float(np.mean(pb)); res['placebo_sd'] = float(np.std(pb))
    return res


def sibling_comparison(df, flag):
    """Polling places that have both flagged urnas and others: weighted Lula share of each set, paired by place."""
    d = df[(df.lula + df.flavio) > 0].copy()
    d['place'] = d.uf + '|' + d.zona.astype(str) + '|' + d.local.astype(str)
    d['flag'] = flag.loc[d.index]
    mixed = d.groupby('place').flag.transform(lambda x: x.any() and not x.all())
    d = d[mixed]
    if not len(d): return None
    agg = d.groupby(['place', 'flag']).agg(L=('lula', 'sum'), F=('flavio', 'sum'), comp=('comp', 'sum'), aptos=('aptos', 'sum')).unstack('flag')
    sL = agg[('L', True)] / (agg[('L', True)] + agg[('F', True)]); sO = agg[('L', False)] / (agg[('L', False)] + agg[('F', False)])
    tL = agg[('comp', True)] / agg[('aptos', True)]; tO = agg[('comp', False)] / agg[('aptos', False)]
    diff = (sL - sO); dt = (tL - tO)
    w = agg[('L', True)] + agg[('F', True)]
    rng = np.random.default_rng(7); vals = diff.values; ww = w.values
    boots = [np.average(vals[i], weights=ww[i]) for i in (rng.integers(0, len(vals), len(vals)) for _ in range(2000))]
    return {'places': int(len(diff)), 'flagged_urnas': int(d.flag.sum()), 'other_urnas': int((~d.flag).sum()),
            'lula_share_flagged': float((agg[('L', True)].sum()) / (agg[('L', True)].sum() + agg[('F', True)].sum())),
            'lula_share_others': float((agg[('L', False)].sum()) / (agg[('L', False)].sum() + agg[('F', False)].sum())),
            'mean_diff_pp': float(np.average(vals, weights=ww) * 100), 'ci_pp': [float(np.percentile(boots, 2.5) * 100), float(np.percentile(boots, 97.5) * 100)],
            'turnout_diff_pp': float(np.average(dt.values, weights=ww) * 100)}


def share_cmp(k1, n1, k0, n0):
    p1, p0 = k1 / n1 if n1 else None, k0 / n0 if n0 else None
    if not n1 or not n0: return {'after': p1, 'before': p0}
    p = (k1 + k0) / (n1 + n0); se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n0)) if 0 < p < 1 else 0
    z = (p1 - p0) / se if se else 0
    return {'after': p1, 'after_ci': wilson(k1, n1), 'after_n': int(n1), 'before': p0, 'before_ci': wilson(k0, n0), 'before_n': int(n0),
            'diff_pp': (p1 - p0) * 100, 'z': z}


def bio_block(x, k):
    n1 = x[f'{k}_all'].sum(); s1 = (x[f'{k}_failed'] + x[f'{k}_noask']).sum()
    n0 = x.h16_all.sum(); s0 = (x.h16_failed + x.h16_noask).sum()
    nd = x.day_all.sum(); sd = x.sem_bio_day.sum()
    return {'sem_biometria': share_cmp(s1, n1, s0, n0), 'failed': share_cmp(x[f'{k}_failed'].sum(), n1, x.h16_failed.sum(), n0),
            'noask': share_cmp(x[f'{k}_noask'].sum(), n1, x.h16_noask.sum(), n0),
            'fast': share_cmp(x[f'{k}_fast'].sum(), n1, x.h16_fast.sum(), n0),
            'unregistered_release_after': int(x[f'{k}_unreg'].sum()), 'failed_after': int(x[f'{k}_failed'].sum()),
            'day_share_sem_biometria': sd / nd if nd else None}

def main():
    TBL, SITE, REPORT = sys.argv[1:4]
    T = pd.read_parquet(TBL)
    mins = pd.read_parquet(TBL.replace('.parquet', '_minutes.parquet'))
    man = json.load(open(os.path.join(SITE, 'data', 'manifest.json')))
    zz = json.load(gzip.open(os.path.join(SITE, 'data', 'ZZ.json.gz')))
    ZL, ZF = sum(zz['urnas']['lula']), sum(zz['urnas']['flavio'])
    T['region'] = T.uf.map(REGION)
    T['unknown'] = np.where(T.has_log, (T.comp - T.n_log).clip(lower=0), T.comp)   # votes with no log time: treat as possibly late
    T['sem_bio_day'] = T.day_failed + T.day_noask
    T['group'] = 'A'
    for g, _, lo, hi in GROUPS: T.loc[(T.close >= lo) & (T.close < hi), 'group'] = g
    T.loc[T.close < 0, 'group'] = '?'
    out = {'generated_from': 'late_votes_table.py + analyze_extension.py', 'cutoffs': [{'key': k, 'label': l, 't': t} for k, l, t in CUTS]}

    # ---------------------------------------------------------------- volume & groups
    tot_votes = int(T.n_log.sum()); tot_comp = int(T.comp.sum())
    out['totals'] = {'urnas': int(len(T)), 'votes_bu': tot_comp, 'votes_log': tot_votes, 'unknown_time_votes': int(T.unknown.sum()),
                     'lula_br': int(T.lula.sum()), 'flavio_br': int(T.flavio.sum()), 'lula_abroad': ZL, 'flavio_abroad': ZF,
                     'branco_br': int(T.branco.sum()), 'nulo_br': int(T.nulo.sum())}
    out['volume'] = {k: {'votes': int(T[f'{k}_all'].sum()), 'share_of_all': T[f'{k}_all'].sum() / tot_votes,
                         'failed': int(T[f'{k}_failed'].sum()), 'noask': int(T[f'{k}_noask'].sum()), 'fast': int(T[f'{k}_fast'].sum()),
                         'urnas_with_late': int((T[f'{k}_all'] > 0).sum())} for k, _, _ in CUTS}
    gr = []
    for g, lab, lo, hi in GROUPS:
        x = T[T.group == g]
        gr.append({'group': g, 'label': lab, 'urnas': int(len(x)), 'share_urnas': len(x) / len(T), 'comp': int(x.comp.sum()),
                   'lula_share': x.lula.sum() / max(1, x.lula.sum() + x.flavio.sum()),
                   **{f'after_{k}': int(x[f'{k}_all'].sum()) for k, _, _ in CUTS},
                   'by_region': {REGION_NAME[r]: int((x.region == r).sum()) for r in REGION_NAME}})
    out['groups'] = gr
    open1701 = T[T.close > 17 * 3600 + 60]
    out['open_at_1701'] = {'urnas': int(len(open1701)), 'stayed_until_1855': int((open1701.close >= 18 * 3600 + 55 * 60).sum())}

    # ---------------------------------------------------------------- geography: by state and region
    st = []
    for uf, x in T.groupby('uf'):
        b = {k: bounds(x, k) for k, _, _ in CUTS}
        st.append({'uf': uf, 'region': REGION[uf], 'urnas': int(len(x)), 'group_D': int((x.group == 'D').sum()), 'group_C': int((x.group == 'C').sum()),
                   'share_D': float((x.group == 'D').mean()), 'lula_share': float(x.lula.sum() / (x.lula.sum() + x.flavio.sum())),
                   'lula_share_D': float(x[x.group == 'D'].lula.sum() / max(1, x[x.group == 'D'].lula.sum() + x[x.group == 'D'].flavio.sum())) if (x.group == 'D').any() else None,
                   'bounds': b, 'biometrics': {k: bio_block(x, k) for k in ('c1700', 'c1710', 'c1800')}})
    out['states'] = sorted(st, key=lambda s: -s['group_D'])
    rg = []
    for r, x in T.groupby('region'):
        rg.append({'region': REGION_NAME[r], 'urnas': int(len(x)), 'group_D': int((x.group == 'D').sum()), 'lula_share': float(x.lula.sum() / (x.lula.sum() + x.flavio.sum())),
                   'after_c1700': int(x.c1700_all.sum()), 'after_c1710': int(x.c1710_all.sum()), 'after_c1800': int(x.c1800_all.sum())})
    out['regions'] = rg
    D = T[T.group == 'D']
    lv = D[D.has_log & (D.last_vote >= 0)]
    out['group_D_detail'] = {'urnas': int(len(D)), 'no_vote_after_1700': int((D.c1700_all == 0).sum()), 'no_vote_after_1710': int((D.c1710_all == 0).sum()),
                             'no_vote_after_1800': int((D.c1800_all == 0).sum()), 'votes': int(D.comp.sum()),
                             'after_1700': int(D.c1700_all.sum()), 'after_1701': int(D.c1701_all.sum()), 'after_1710': int(D.c1710_all.sum()),
                             'after_1730': int(D.c1730_all.sum()), 'after_1800': int(D.c1800_all.sum()), 'after_1900': int(D.c1900_all.sum()),
                             'max_after_1710_one_urna': int(D.c1710_all.max()),
                             'last_vote_quantiles': {str(q): int(v) for q, v in lv.last_vote.quantile([.25, .5, .75, .95, .99]).items()},
                             'share_last_vote_before_1710': float((lv.last_vote <= 17 * 3600 + 600).mean())}
    out['group_D_lean'] = {'urnas': int(len(D)), 'in_lula_majority_munis': None,
                           'lula_share_D_urnas': float(D.lula.sum() / (D.lula.sum() + D.flavio.sum())),
                           'lula_share_brazil': float(T.lula.sum() / (T.lula.sum() + T.flavio.sum()))}
    mun_share = T.groupby(['uf', 'ibge']).apply(lambda x: x.lula.sum() / max(1, x.lula.sum() + x.flavio.sum()), include_groups=False)
    T['mun_lula_share'] = [mun_share[(a, b)] for a, b in zip(T.uf, T.ibge)]
    out['group_D_lean']['in_lula_majority_munis'] = int((T.loc[D.index, 'mun_lula_share'] > 0.5).sum()) if len(D) else 0

    # ---------------------------------------------------------------- hard-stop bounds: country (with abroad, unaffected), munis
    out['national'] = {k: bounds(T, k, ZL, ZF) for k, _, _ in CUTS}
    ext = dict(out['national']['c1700']); ext['margin_min'] -= ZL; ext['max_lula_removed'] += ZL
    ext['winner_can_change'] = bool(ext['margin_min'] <= 0)
    ext['note'] = 'Cenário extremo: além de todos os votos após 17:00 no Brasil, também todos os votos do exterior removidos como se fossem de Lula.'
    out['national_abroad_also_removable'] = ext
    flips = {}
    for k, _, _ in CUTS:
        g = T.groupby(['uf', 'ibge', 'muni']).apply(lambda x: bounds(x, k), include_groups=False)
        fl = [{'uf': a, 'ibge': b, 'muni': c, **v} for (a, b, c), v in g.items() if v['winner_can_change'] or v['tie_possible']]
        flips[k] = {'munis_total': int(len(g)), 'munis_flip_possible': sum(v['winner_can_change'] for v in fl),
                    'munis_tie_possible': sum(v['tie_possible'] and not v['winner_can_change'] for v in fl),
                    'list': sorted(fl, key=lambda v: abs(v['margin']))[:50]}
    out['muni_flips'] = flips

    # ---------------------------------------------------------------- lean estimates (model-based, labelled as such)
    def prop(k):
        kk = T[f'{k}_all'].values; Tt = T.comp.clip(lower=1).values
        return {'lula': float((kk * T.lula.values / Tt).sum()), 'flavio': float((kk * T.flavio.values / Tt).sum()),
                'lula_share': float((kk * T.lula.values / Tt).sum() / max(1e-9, (kk * (T.lula.values + T.flavio.values) / Tt).sum()))}
    out['lean_if_like_their_urna'] = {k: prop(k) for k, _, _ in CUTS}
    out['place_regression'] = {k: place_regression(T, k) for k in ('c1700', 'c1710', 'c1800')}
    out['sibling_D_vs_ontime'] = sibling_comparison(T, T.group == 'D')
    out['sibling_CD_vs_AB'] = sibling_comparison(T, T.group.isin(['C', 'D']))

    # ---------------------------------------------------------------- biometrics / fast votes after vs before (same urnas)
    out['biometrics'] = {'all_urnas': {k: bio_block(T, k) for k in ('c1700', 'c1710', 'c1800')},
                         'group_D': {k: bio_block(D, k) for k in ('c1700', 'c1710', 'c1800')}}
    out['biometrics']['note'] = ('"before" = votos entre 16:00 e 17:00 nas mesmas urnas (mesmo perfil de fim de dia); '
                                 '"sem biometria" = falha na leitura (liberado pelo mesário) + urna não pediu a digital.')

    # ---------------------------------------------------------------- minute series (national; group D)
    gmap = dict(zip(zip(T.uf, T.ui), T.group))
    mins['group'] = [gmap.get(k, '?') for k in zip(mins.uf, mins.ui)]
    ser = {}
    for name, sel in (('all', mins), ('D', mins[mins.group == 'D'])):
        p = sel.groupby(['minute', 'kind']).n.sum().unstack(fill_value=0)
        rng = range(16 * 60, 23 * 60 + 10)
        p = p.reindex(rng, fill_value=0)
        ser[name] = {'t0_minute': 16 * 60, 'bio': p.get('bio', pd.Series(0, index=p.index)).astype(int).tolist(),
                     'failed': p.get('failed', pd.Series(0, index=p.index)).astype(int).tolist(),
                     'noask': p.get('noask', pd.Series(0, index=p.index)).astype(int).tolist()}
    openm = []
    for mm in range(16 * 60, 23 * 60 + 10):
        t = mm * 60
        openm.append(int(((T.close > t)).sum()))
    ser['open_urnas'] = openm
    out['minute_series'] = ser

    # ---------------------------------------------------------------- top urnas / munis, data quality
    T['late1710'] = T.c1710_all + T.unknown * 0
    top = T.sort_values('c1710_all', ascending=False).head(40)
    out['top_urnas_after_1710'] = [{'uf': r.uf, 'muni': r.muni, 'zona': int(r.zona), 'secao': int(r.secao), 'close': int(r.close), 'comp': int(r.comp),
                                    'after_1700': int(r.c1700_all), 'after_1710': int(r.c1710_all), 'after_1800': int(r.c1800_all),
                                    'lula_share': r.lula / max(1, r.lula + r.flavio), 'sem_bio_after_1700': int(r.c1700_failed + r.c1700_noask)}
                                   for r in top.itertuples()]
    mt = T.groupby(['uf', 'ibge', 'muni']).agg(D=('group', lambda g: int((g == 'D').sum())), after_1700=('c1700_all', 'sum'), after_1710=('c1710_all', 'sum'),
                                               L=('lula', 'sum'), F=('flavio', 'sum'), urnas=('ui', 'size')).reset_index()
    mt['lula_share'] = mt.L / (mt.L + mt.F)
    out['top_munis_D'] = mt.sort_values('D', ascending=False).head(30).drop(columns=['L', 'F']).to_dict('records')
    out['top_munis_after_1710'] = mt.sort_values('after_1710', ascending=False).head(30).drop(columns=['L', 'F']).to_dict('records')
    q = {}
    q['votes_after_own_close'] = int(((T.last_vote > T.close + 60) & (T.close >= 0) & T.has_log).sum())
    q['first_vote_before_0800'] = int(((T.first_vote >= 0) & (T.first_vote < 8 * 3600)).sum())
    q['no_log_urnas'] = int((~T.has_log).sum())
    q['latest_closings'] = [{'uf': r.uf, 'muni': r.muni, 'zona': int(r.zona), 'secao': int(r.secao), 'close': int(r.close), 'last_vote': int(r.last_vote),
                             'first_vote': int(r.first_vote), 'comp': int(r.comp), 'after_1900': int(r.c1900_all)}
                            for r in T.sort_values('close', ascending=False).head(10).itertuples()]
    out['data_quality'] = q

    # ---------------------------------------------------------------- per-municipality data for the site
    mun_out = {}
    for uf, x in T.groupby('uf'):
        g = x.groupby('ibge')
        rec = {'ibge': list(g.groups.keys())}
        for k, _, _ in CUTS:
            kk = x[f'{k}_all'] + x.unknown
            rec[f'{k}_all'] = g[f'{k}_all'].sum().astype(int).tolist()
            rec[f'{k}_sem_bio'] = (g[f'{k}_failed'].sum() + g[f'{k}_noask'].sum()).astype(int).tolist()
            rec[f'{k}_max_lula'] = np.minimum(kk, x.lula).groupby(x.ibge).sum().astype(int).tolist()
            rec[f'{k}_max_flavio'] = np.minimum(kk, x.flavio).groupby(x.ibge).sum().astype(int).tolist()
        rec['h16_all'] = g.h16_all.sum().astype(int).tolist()
        rec['h16_sem_bio'] = (g.h16_failed.sum() + g.h16_noask.sum()).astype(int).tolist()
        rec['comp'] = g.comp.sum().astype(int).tolist()
        rec['lula'] = g.lula.sum().astype(int).tolist(); rec['flavio'] = g.flavio.sum().astype(int).tolist()
        rec['group_D'] = g.group.apply(lambda s: int((s == 'D').sum())).tolist()
        rec['group_C'] = g.group.apply(lambda s: int((s == 'C').sum())).tolist()
        rec['unknown'] = g.unknown.sum().astype(int).tolist()
        mun_out[uf] = rec
    urn_out = T[(T.group.isin(['C', 'D'])) | (T.c1710_all > 0)][['uf', 'ibge', 'zona', 'secao', 'local', 'close', 'comp', 'lula', 'flavio',
                                                                *[f'{k}_all' for k, _, _ in CUTS], 'c1700_failed', 'c1700_noask', 'group']]
    out = clean(out)
    site_payload = clean({k: v for k, v in out.items()} | {'munis': mun_out, 'urnas_late': {c: urn_out[c].tolist() for c in urn_out.columns}})
    with gzip.open(os.path.join(SITE, 'data', 'extension.json.gz'), 'wt', encoding='utf-8') as fh:
        json.dump(site_payload, fh, ensure_ascii=False, separators=(',', ':'), default=lambda o: o.item() if hasattr(o, 'item') else str(o), allow_nan=False)
    json.dump(out, open(REPORT.replace('.md', '.json'), 'w'), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
    print(json.dumps({'volume': out['volume'], 'groups': [{k: g[k] for k in ('group', 'urnas', 'after_c1700', 'after_c1710', 'lula_share')} for g in gr],
                      'national_c1700': out['national']['c1700'], 'flips': {k: v['munis_flip_possible'] for k, v in flips.items()}}, indent=1, default=str))


if __name__ == '__main__':
    main()
