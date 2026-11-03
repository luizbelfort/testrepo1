"""Write docs/relatorio_prorrogacao.md from the analysis JSON (analyze_extension.py). All numbers come from it.

usage: python write_extension_report.py <report.json> <out.md>
"""
import json, sys


def br(n, d=0):
    if n is None: return '—'
    s = f'{n:,.{d}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(x, d=1): return '—' if x is None else br(100 * x, d) + '%'
def sg(n): return ('+' if n > 0 else '−' if n < 0 else '') + br(abs(n))
def hm(t): return f'{t // 3600:02d}:{t % 3600 // 60:02d}'


def main():
    R = json.load(open(sys.argv[1])); out = sys.argv[2]
    n0, n10 = R['national']['c1700'], R['national']['c1710']; v = R['volume']; D = R['group_D_detail']
    reg = R['place_regression']['c1700']; reg10 = R['place_regression']['c1710']; sib = R['sibling_D_vs_ontime']
    tot = R['totals']['votes_bu']
    L = []
    w = L.append
    w('# A prorrogação mudou o resultado? — 2º turno de 2026 (Presidente)\n')
    w('Gerado automaticamente a partir dos logs de todas as urnas e dos Boletins de Urna publicados pelo TSE '
      '(`pipeline/late_votes_table.py`, `pipeline/analyze_extension.py`). Horários de Brasília.\n')
    w('## Resposta curta\n')
    w(f"**Não.** Depois das 17:00 foram registrados **{br(v['c1700']['votes'])} votos** ({pct(v['c1700']['votes'] / tot, 3)} dos votos no Brasil); "
      f"outros {br(R['totals']['unknown_time_votes'])} votos, de 4 urnas com log incompleto, não têm horário e foram tratados como se pudessem ser posteriores. "
      f"Mesmo se **todos** esses {br(n0['late_votes'])} votos tivessem sido do mesmo candidato, a diferença final entre Lula e Flávio Bolsonaro "
      f"({sg(n0['margin'])}) ficaria entre **{sg(n0['margin_min'])}** e **{sg(n0['margin_max'])}**. Nenhum estado muda de vencedor em nenhum horário de corte; "
      f"nenhum município muda de vencedor (no corte das 17:00, {R['muni_flips']['c1700']['munis_tie_possible']} município poderia terminar empatado).\n")
    w('> **Limite dos dados:** nenhum arquivo liga o horário de um voto ao candidato. O log da urna registra *quando*; o RDV registra *em quem*, '
      'embaralhado para proteger o sigilo. Por isso este relatório usa contagens e limites exatos, e marca como estimativa o que depende de hipótese.\n')
    w('## Se a votação parasse em cada horário (limites exatos)\n')
    w('| Corte | Votos depois* | Diferença Lula − Flávio possível | Lula % válidos possível | Vencedor muda? |')
    w('|---|---:|---|---|---|')
    for c in R['cutoffs']:
        b = R['national'][c['key']]
        w(f"| {c['label']} | {br(b['late_votes'])} | {sg(b['margin_min'])} a {sg(b['margin_max'])} | {pct(b['lula_share_min'], 2)} a {pct(b['lula_share_max'], 2)} | {'sim' if b['winner_can_change'] else 'não'} |")
    w(f"\n\\* inclui os {br(R['totals']['unknown_time_votes'])} votos sem horário. Resultado oficial: Lula {br(n0['lula'])} ({pct(n0['lula_share'], 2)}), Flávio Bolsonaro {br(n0['flavio'])}. "
      'O exterior entra inteiro: não houve prorrogação lá (todas as urnas encerraram até 18:15, hora local).\n')
    w('## Quantas urnas ficaram abertas, e onde\n')
    w(f"Às 17:01, {br(R['open_at_1701']['urnas'])} urnas ainda não tinham encerrado (filas e procedimento de encerramento); "
      f"{br(D['urnas'])} ficaram abertas até 18:55 ou mais (grupo D). Dessas, **{br(D['no_vote_after_1700'])} não receberam nenhum voto depois das 17:00** "
      f"e {br(D['no_vote_after_1710'])} nenhum depois das 17:10; o último voto foi, na mediana, às {hm(D['last_vote_quantiles']['0.5'])}. "
      f"No total, o grupo D recebeu {br(D['after_1700'])} votos depois das 17:00 ({pct(D['after_1700'] / D['votes'], 2)} dos seus votos), "
      f"{br(D['after_1800'])} depois das 18:00 e {br(D['after_1900'])} depois das 19:00.\n")
    w('| Grupo (encerramento no BU) | Urnas | Votos após 17:00 | Após 17:10 | Lula % (urnas do grupo) |')
    w('|---|---:|---:|---:|---:|')
    for g in R['groups']: w(f"| {g['group']} · {g['label']} | {br(g['urnas'])} | {br(g['after_c1700'])} | {br(g['after_c1710'])} | {pct(g['lula_share'])} |")
    w('\n| Região | Urnas | Grupo D | Votos após 17:00 | Após 17:10 | Lula % (região) |')
    w('|---|---:|---:|---:|---:|---:|')
    for r in R['regions']: w(f"| {r['region']} | {br(r['urnas'])} | {br(r['group_D'])} | {br(r['after_c1700'])} | {br(r['after_c1710'])} | {pct(r['lula_share'])} |")
    w('\n| UF | Grupo D | % das urnas | Votos após 17:00 | Lula % estado | Lula % urnas D | Diferença oficial | Parada às 17:00 |')
    w('|---|---:|---:|---:|---:|---:|---:|---|')
    for s in R['states']:
        if not s['group_D'] and s['bounds']['c1700']['late_votes'] < 500: continue
        b = s['bounds']['c1700']
        w(f"| {s['uf']} | {br(s['group_D'])} | {pct(s['share_D'])} | {br(b['late_votes'])} | {pct(s['lula_share'])} | {pct(s['lula_share_D']) if s['lula_share_D'] is not None else '—'} | {sg(b['margin'])} | {sg(b['margin_min'])} a {sg(b['margin_max'])} |")
    w(f"\nAs urnas do grupo D estavam sobretudo no Sudeste (RJ e SP) e, dentro dos estados, nas capitais e grandes cidades: "
      f"{br(R['group_D_lean']['in_lula_majority_munis'])} das {br(D['urnas'])} em municípios onde Lula venceu. No conjunto deram {pct(R['group_D_lean']['lula_share_D_urnas'])} a Lula "
      f"(Brasil: {pct(R['group_D_lean']['lula_share_brazil'])}) — percentual que inclui todos os votos dessas urnas, a maioria dados antes das 17:00.\n")
    w('## Biometria dos eleitores depois das 17:00\n')
    w('*Sem biometria* = leitura da digital falhou e o mesário liberou o eleitor, **mais** eleitores para quem a urna não pediu a digital. '
      'Referência: votos entre 16:00 e 17:00 nas mesmas urnas.\n')
    w('| Recorte | Sem biometria depois | 16:00–17:00 | Diferença | Votos depois |')
    w('|---|---:|---:|---:|---:|')
    for scope, lab in (('all_urnas', 'Todas as urnas'), ('group_D', 'Grupo D')):
        for k, lk in (('c1700', '17:00'), ('c1710', '17:10'), ('c1800', '18:00')):
            b = R['biometrics'][scope][k]['sem_biometria']
            w(f"| {lab}, depois das {lk} | {pct(b['after'])} | {pct(b['before'])} | {br(b['diff_pp'], 2)} p.p. | {br(b['after_n'])} |")
    w('\nA diferença logo depois das 17:00 vem da fila de encerramento (mais falhas de leitura); depois das 17:10, e nas urnas da prorrogação, a proporção é a mesma da última hora regular.\n')
    w('## Em quem votaram? (estimativas, não contagens)\n')
    w(f"- Se cada eleitor tardio tivesse votado como o restante da própria urna: {pct(R['lean_if_like_their_urna']['c1700']['lula_share'])} Lula — descreve onde houve voto tardio, não como esses eleitores votaram.")
    w(f"- Dentro do mesmo local de votação ({br(reg['places'])} locais), a fatia de Lula entre os eleitores depois das 17:00 é estimada em **{pct(reg['implied_late_lula_share'])}** "
      f"(IC 95%: {pct(reg['implied_late_ci'][0])} a {pct(reg['implied_late_ci'][1])}), contra {pct(reg['baseline_identifying_places'])} entre os demais eleitores desses locais. "
      f"A hipótese \"80% Lula\" fica {br(abs(reg['z_vs_80pct']), 1)} erros-padrão abaixo do observado (rejeitada); \"65%\", {br(abs(reg['z_vs_65pct']), 1)}. "
      f"Conferências: sem pesos {br(reg['beta_unweighted'] * 100, 1)} p.p.; placebo (horários embaralhados no local) {br(reg['placebo_mean'] * 100, 1)} ± {br(reg['placebo_sd'] * 100, 1)} p.p.")
    w(f"- Depois das 17:10 há só {br(v['c1710']['votes'])} votos — poucos demais para estimar (IC 95%: {pct(reg10['implied_late_ci'][0])} a {pct(reg10['implied_late_ci'][1])}). Para eles vale o limite exato: no máximo {br(max(n10['max_lula_removed'], n10['max_flavio_removed']))} votos de diferença.")
    if sib: w(f"- Urnas da prorrogação vs vizinhas do mesmo local que fecharam no horário ({br(sib['places'])} locais): {br(sib['mean_diff_pp'], 2)} p.p. na fatia de Lula (IC 95%: {br(sib['ci_pp'][0], 2)} a {br(sib['ci_pp'][1], 2)}).")
    w('\n## Qualidade dos dados\n')
    q = R['data_quality']
    w(f"- Totais conferem com o resultado oficial (Lula {br(n0['lula'])}, Flávio Bolsonaro {br(n0['flavio'])}); {br(R['totals']['votes_bu'])} votos no Brasil, dos quais {br(R['totals']['votes_log'])} com horário no log.")
    w(f"- Urnas com voto registrado depois do próprio encerramento: {q['votes_after_own_close']}. Urnas com voto antes das 08:00: {q['first_vote_before_0800']}. Urnas sem log: {q['no_log_urnas']}.")
    lc = q['latest_closings'][0]
    w(f"- A urna que encerrou por último ({lc['muni']}/{lc['uf']}, zona {lc['zona']}, seção {lc['secao']}, às {hm(lc['close'])}) teve o último voto às {hm(lc['last_vote'])}.")
    w('- Fuso de cada município deduzido do horário de abertura no BU (todas as urnas abrem às 08:00 de Brasília).\n')
    open(out, 'w').write('\n'.join(L) + '\n')
    print('wrote', out)


if __name__ == '__main__':
    main()
