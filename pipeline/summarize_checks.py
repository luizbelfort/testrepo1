"""Summarise per-urna verification (verify_urnas.py) and the anomaly scan (anomaly_scan.py) for the site.

Outputs:
  site/data/conferencias.json.gz       national + per-state tallies, failing urnas, flag lists (capped), method text
  site/data/conferencias/*.csv         full downloadable lists (one row per urna)

usage: python summarize_checks.py <verify dir> <anomaly.parquet> <site dir>
"""
import glob, gzip, json, math, os, re, sys
import numpy as np, pandas as pd

UFS_ORDER = None
CHECKS = [
    ('files', 'Os 5 arquivos publicados (BU, RDV, imagem do BU, log, assinaturas)'),
    ('sig_decode', 'Arquivo de assinaturas (vota.vsc) lido'),
    ('sw_self', 'Assinatura de software: hash do próprio conteúdo confere'),
    ('hw_self', 'Assinatura da urna (hardware): hash do próprio conteúdo confere'),
    ('sw_hashes', 'Hash SHA-512 de BU, RDV, imagem do BU e log = lista assinada (software)'),
    ('hw_hashes', 'Hash SHA-512 de BU, RDV, imagem do BU e log = lista assinada (urna)'),
    ('cert_urna', 'Certificado da urna: número no certificado = número interno da urna no BU'),
    ('cert_valid', 'Certificado da urna válido em 25/10/2026'),
    ('bu_decode', 'BU lido'),
    ('rdv_decode', 'RDV lido'),
    ('bu_rdv', 'RDV = BU (Lula, Flávio, brancos, nulos e total, voto a voto)'),
    ('bu_bweb', 'BU = planilha bweb do TSE (Lula, Flávio, comparecimento, aptos)'),
    ('hab_sum', 'Habilitações no BU (código + biometria + outras) = comparecimento'),
]
PUBLISHED = {'bu.dat', 'rdv.dat', 'imgbu.dat', 'log.jez', 'vota.vsc'}


def load_bweb(site):
    rows = []
    for p in sorted(glob.glob(os.path.join(site, 'data', '*.json.gz'))):
        if not re.fullmatch(r'[A-Z]{2}\.json\.gz', os.path.basename(p)): continue
        d = json.load(gzip.open(p)); uf = os.path.basename(p)[:2]
        if d.get('abroad') or 'urnas' not in d: continue
        u, m = d['urnas'], d['munis']
        tse = [int(m['tse'][x]) for x in u['m']]
        rows.append(pd.DataFrame({'key': [f"o03221{uf.lower()}{t:05d}{z:04d}{s:04d}" for t, z, s in zip(tse, u['z'], u['s'])],
                                  'uf': uf, 'muni': [m['name'][x] for x in u['m']], 'ibge': [m['ibge'][x] for x in u['m']],
                                  'w_lula': u['lula'], 'w_flavio': u['flavio'], 'w_comp': u['comp'], 'w_aptos': u['aptos']}))
    return pd.concat(rows, ignore_index=True)


def verification(vdir, site):
    R = []
    for p in sorted(glob.glob(os.path.join(vdir, '*.jsonl'))):
        uf = os.path.basename(p)[:2]
        seen = {}
        for l in open(p):
            r = json.loads(l); r['uf'] = uf; seen[r['key']] = r   # keep the last attempt per urna
        R += list(seen.values())
    V = pd.DataFrame(R)
    W = load_bweb(site)
    V = V.merge(W.drop(columns='uf'), on='key', how='left')
    g = lambda c, d=0: V[c].fillna(d) if c in V else pd.Series(d, index=V.index)
    res = pd.DataFrame({'key': V.key, 'uf': V.uf})
    res['files'] = V.get('files', pd.Series('', index=V.index)).fillna('').map(lambda s: PUBLISHED <= set(s.split(',')))
    ok = lambda c: V[c].isna() if c in V else pd.Series(True, index=V.index)
    res['sig_decode'] = ok('fetch_error') & ok('sig_error')
    res['sw_self'] = g('sw_self_ok', False).astype(bool)
    res['hw_self'] = g('hw_self_ok', False).astype(bool)
    for t in ('sw', 'hw'):
        res[f'{t}_hashes'] = (g(f'{t}_hash_bad', 1) == 0) & (g(f'{t}_hash_ok') >= 4) & (g(f'{t}_not_listed', '').astype(str).isin(['', 'nan']))
    res['cert_urna'] = g('cert_matches_urna', False).astype(bool)
    res['cert_valid'] = g('cert_valid_day', False).astype(bool)
    res['bu_decode'] = ok('fetch_error') & ok('bu_error')
    res['rdv_decode'] = ok('fetch_error') & ok('rdv_error') & (g('rdv_sa') == 0)
    eq = np.ones(len(V), bool)
    for k in ('lula', 'flavio', 'branco', 'nulo'): eq &= g('bu_' + k).values == g('rdv_' + k).values
    eq &= g('rdv_n').values == g('bu_comp_pres').values
    res['bu_rdv'] = eq & res.bu_decode & res.rdv_decode
    res['bu_bweb'] = ((g('bu_lula') == g('w_lula', -1)) & (g('bu_flavio') == g('w_flavio', -1)) & (g('bu_comp') == g('w_comp', -1)) & (g('bu_aptos') == g('w_aptos', -1))) & res.bu_decode
    res['hab_sum'] = (g('bu_hab_code') + g('bu_hab_bio') + g('bu_hab_other')) == g('bu_comp')
    detail_cols = ['key', 'uf', 'muni', 'model', 'cert_issuer', 'bu_comp', 'bu_aptos', 'bu_lula', 'bu_flavio', 'bu_branco', 'bu_nulo',
                   'rdv_n', 'rdv_lula', 'rdv_flavio', 'rdv_branco', 'rdv_nulo', 'w_lula', 'w_flavio', 'w_comp', 'w_aptos',
                   'bu_hab_code', 'bu_hab_bio', 'bu_hab_other', 'sw_mismatch', 'hw_mismatch', 'fetch_error', 'sig_error', 'bu_error', 'rdv_error']
    D = V[[c for c in detail_cols if c in V]].copy()
    return V, res, D


def tallies(res, by=None):
    out = []
    groups = [('BR', res)] if by is None else list(res.groupby(by))
    for name, R in groups:
        row = {'scope': name, 'urnas': int(len(R))}
        for c, _ in CHECKS: row[c] = int(R[c].sum())
        out.append(row)
    return out


def flags(A):
    A = A.copy()
    A['turnout'] = A.comp / A.aptos.clip(lower=1)
    from scipy import stats
    g = A.groupby(['uf', 'ibge'])
    ref = (g.unreg.transform('sum') / g.failed.transform('sum').clip(lower=1)).clip(1e-6, 1 - 1e-6)
    A['p_unreg_high'] = stats.binom.sf(A.unreg - 1, A.failed, ref)
    F = {
        'falha_biometria_alta': ('Falha de leitura da digital muito acima do município (p < 1e-7) e ≥ 30% dos eleitores',
                                 (A.p_failed_high < 1e-7) & (A.failed_rate >= 0.30)),
        'sequencia_falhas': ('Sequência de falhas de leitura seguidas improvável ao acaso (p < 1e-7) e ≥ 10 seguidas',
                             (A.p_run < 1e-7) & (A.run_failed >= 10)),
        'votos_rapidos': ('3 ou mais votos "rápidos": digital falhou, liberação pelo mesário ≤ 10 s, voto ≤ 5 s',
                          A.fast >= 3),
        'comparecimento_alto': ('Comparecimento ≥ 97% (com ≥ 50 aptos) ou 4+ desvios-padrão acima do município',
                                ((A.turnout >= 0.97) & (A.aptos >= 50)) | (A.turnout_z >= 4)),
        'liberacao_digital_nao_cadastrada': ('Liberações confirmadas com digital não cadastrada muito acima do município (p < 1e-10) e ≥ 20',
                                             (A.p_unreg_high < 1e-10) & (A.unreg >= 20)),
        'falha_dados': ('5 ou mais falhas de conferência de dados do eleitor', A.data_fail >= 5),
        'habilitado_sem_voto': ('3 ou mais eleitores habilitados que não concluíram o voto', A.hab_no_vote >= 3),
    }
    return F


def within_muni_corr(A, x, y):
    d = A[[x, y, 'uf', 'ibge', 'n']].dropna()
    for c in (x, y): d[c + '_dm'] = d[c] - d.groupby(['uf', 'ibge'])[c].transform('mean')
    w = d.n; a, b = d[x + '_dm'], d[y + '_dm']
    return float((w * a * b).sum() / math.sqrt((w * a * a).sum() * (w * b * b).sum()))


def main():
    vdir, apath, site = sys.argv[1:4]
    outdir = os.path.join(site, 'data', 'conferencias'); os.makedirs(outdir, exist_ok=True)
    J = {'checks': [{'key': k, 'label': l} for k, l in CHECKS]}
    if glob.glob(os.path.join(vdir, '*.jsonl')):
        V, res, D = verification(vdir, site)
        J['verify_national'] = tallies(res)[0]
        J['verify_states'] = tallies(res, 'uf')
        bad = res[[c for c, _ in CHECKS]].all(axis=1) == False
        fails = res[bad].merge(D, on=['key', 'uf'], how='left')
        fails['failed_checks'] = fails[[c for c, _ in CHECKS]].apply(lambda r: ','.join(c for c, _ in CHECKS if not r[c]), axis=1)
        keep = ['key', 'uf', 'muni', 'failed_checks'] + [c for c in D.columns if c not in ('key', 'uf', 'muni')]
        fails[keep].to_csv(os.path.join(outdir, 'conferencia_falhas.csv'), index=False)
        J['verify_fail_by_check'] = {c: int((~res[c]).sum()) for c, _ in CHECKS}
        J['verify_fail_list'] = json.loads(fails[keep].head(500).to_json(orient='records'))
        J['verify_fail_total'] = int(bad.sum())
        J['cert_issuers'] = {str(k): int(v) for k, v in V.get('cert_issuer', pd.Series(dtype=str)).fillna('—').value_counts().items()}
        J['models'] = {str(k): int(v) for k, v in V.get('model', pd.Series(dtype=str)).fillna('—').value_counts().items()}
        J['unpublished_signed_files'] = 'jufa.dat, imgze.dat, hash.dat, wsqbio.jez, wsqman.jez, wsqmes.jez, mr.ver'
        res.to_csv(os.path.join(outdir, 'conferencia_por_urna.csv.gz'), index=False, compression='gzip')
    if os.path.exists(apath):
        A = pd.read_parquet(apath)
        F = flags(A)
        nat_lula = float(A.lula.sum() / (A.lula + A.flavio).sum())
        lst = []
        cols = ['uf', 'muni', 'zona', 'secao', 'local', 'model', 'aptos', 'comp', 'n', 'failed', 'noask', 'bio', 'failed_rate', 'mun_failed_rate',
                'p_failed_high', 'run_failed', 'p_run', 'fast', 'vfast_failed', 'unreg', 'data_fail', 'hab_no_vote', 'turnout', 'turnout_z', 'lula', 'flavio', 'lula_share']
        A['turnout'] = A.comp / A.aptos.clip(lower=1)
        for k, (label, m) in F.items():
            S = A[m]
            S[cols].sort_values(['uf', 'muni', 'zona', 'secao']).to_csv(os.path.join(outdir, f'sinal_{k}.csv'), index=False)
            lw = int((S.lula > S.flavio).sum()); fw = int((S.flavio > S.lula).sum())
            lst.append({'key': k, 'label': label, 'urnas': int(len(S)), 'votes': int(S.n.sum()),
                        'lula_won': lw, 'flavio_won': fw, 'tied': int(len(S) - lw - fw),
                        'lula_share': float(S.lula.sum() / max(1, (S.lula + S.flavio).sum())) if len(S) else None,
                        'states': {str(u): int(c) for u, c in S.uf.value_counts().head(27).items()},
                        'rows': json.loads(S.sort_values('n', ascending=False)[cols].head(200).to_json(orient='records'))})
        anym = np.zeros(len(A), bool)
        for _, (_, m) in F.items(): anym |= m.values
        J['anomaly'] = {
            'urnas_scanned': int(len(A)), 'votes_scanned': int(A.n.sum()),
            'lula_share_all': nat_lula,
            'lula_won_all': int((A.lula > A.flavio).sum()), 'flavio_won_all': int((A.flavio > A.lula).sum()),
            'any_flag_urnas': int(anym.sum()), 'any_flag_votes': int(A.n[anym].sum()),
            'any_flag_lula_share': float(A.lula[anym].sum() / max(1, (A.lula + A.flavio)[anym].sum())),
            'flags': lst,
            'corr_within_muni': {
                'failed_rate_vs_lula_share': within_muni_corr(A, 'failed_rate', 'lula_share'),
                'failed_rate_vs_turnout': within_muni_corr(A, 'failed_rate', 'turnout'),
                'noask_rate_vs_lula_share': within_muni_corr(A.assign(noask_rate=A.noask / A.n.clip(lower=1)), 'noask_rate', 'lula_share'),
                'fast_rate_vs_lula_share': within_muni_corr(A.assign(fast_rate=A.fast / A.n.clip(lower=1)), 'fast_rate', 'lula_share'),
            },
            'by_model': [{'model': str(k), 'urnas': int(len(G)), 'failed_rate': float(G.failed.sum() / G.n.sum()),
                          'noask_rate': float(G.noask.sum() / G.n.sum()), 'lula_share': float(G.lula.sum() / max(1, (G.lula + G.flavio).sum()))}
                         for k, G in A.groupby('model')],
            'unreg_urnas_any': int((A.unreg > 0).sum()),
            'totals': {'failed': int(A.failed.sum()), 'noask': int(A.noask.sum()), 'bio': int(A.bio.sum()), 'fast': int(A.fast.sum()),
                       'unreg': int(A.unreg.sum()), 'data_fail': int(A.data_fail.sum()), 'hab_no_vote': int(A.hab_no_vote.sum())},
        }
    with gzip.open(os.path.join(site, 'data', 'conferencias.json.gz'), 'wt') as fh:
        json.dump(J, fh, ensure_ascii=False, allow_nan=False, default=lambda o: None)
    print(json.dumps({k: v for k, v in J.items() if k in ('verify_national', 'verify_fail_by_check', 'cert_issuers', 'models', 'verify_fail_total')}, ensure_ascii=False, indent=1))
    if 'anomaly' in J: print(json.dumps({k: v for k, v in J['anomaly'].items() if k != 'flags'}, indent=1), [(f['key'], f['urnas'], f['lula_won'], f['flavio_won']) for f in J['anomaly']['flags']])


if __name__ == '__main__':
    main()
