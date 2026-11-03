// Report page: "A prorrogação em números". Every number comes from data/extension.json.gz
// (pipeline/late_votes_table.py + pipeline/analyze_extension.py).
import { getJSON, setDataVersion } from './data.js?v=20261103g';
import { areaChart } from './charts.js?v=20261103g';
import { fmtInt, pct, hhmm, hhmmss } from './scales.js?v=20261103g';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const signed = n => (n > 0 ? '+' : n < 0 ? '−' : '') + fmtInt(Math.abs(n));
const pp = (x, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d).replace('.', ',')} p.p.`);
const sh = (x, d = 1) => pct(x, d);

async function main() {
  const M = await getJSON('data/manifest.json');
  setDataVersion(M.generated);
  const E = await getJSON('data/extension.json.gz');
  const c = M.election.candidates, L = c[0], F = c[1];
  const n = E.national, n0 = n.c1700, n10 = n.c1710, v = E.volume, D = E.group_D_detail;
  const statesChange = k => E.states.filter(s => s.bounds[k].winner_can_change).length;
  const maxShift = Math.max(n0.max_lula_removed, n0.max_flavio_removed);
  const reg = E.place_regression.c1700, sib = E.sibling_D_vs_ontime;
  const flip0 = E.muni_flips.c1700;
  const total = E.totals.votes_bu + 0;

  const t0 = E.minute_series.all.t0_minute * 60;
  const sections = [];
  sections.push(`
  <h1>A prorrogação mudou o resultado?</h1>
  <p class="lede">Análise de todas as ${fmtInt(E.totals.urnas)} urnas do Brasil (mais ${fmtInt(M.states.find(s => s.uf === 'ZZ')?.urnas || 0)} no exterior), a partir dos logs das urnas e dos Boletins de Urna publicados pelo TSE. Horários de Brasília.</p>
  <div class="answer"><b>Não.</b> Depois das 17:00 foram registrados <b>${fmtInt(v.c1700.votes)} votos</b> — ${pct(v.c1700.votes / total, 3)} de todos os votos no Brasil (outros ${fmtInt(E.totals.unknown_time_votes)} votos, de urnas com log incompleto, não têm horário e foram contados como se pudessem ser posteriores). Mesmo no caso extremo em que <b>todos esses ${fmtInt(n0.late_votes)} votos</b> tivessem sido do mesmo candidato, a diferença entre ${esc(L.name)} e ${esc(F.name)} (${signed(n0.margin)} votos) ficaria entre <b>${signed(n0.margin_min)}</b> e <b>${signed(n0.margin_max)}</b>. Nenhum estado muda de vencedor em nenhum horário de corte; ${flip0.munis_flip_possible ? `${flip0.munis_flip_possible} município poderia mudar` : 'nenhum município muda de vencedor'}${flip0.munis_tie_possible ? ` (${flip0.munis_tie_possible} poderia terminar empatado)` : ''}.</div>
  <div class="caveat"><b>O que não é possível saber, e por quê:</b> nenhum arquivo registra, ao mesmo tempo, o horário e o candidato de um voto. O log da urna guarda o horário de cada voto, mas não em quem; o Registro Digital do Voto guarda em quem, embaralhado de propósito para proteger o sigilo do voto. Por isso este relatório trabalha com <b>contagens exatas</b> e <b>limites exatos</b>, e marca como estimativa tudo o que depende de hipótese.</div>
  <div class="tiles">
    <div class="tile"><div class="k">Votos registrados depois das 17:00</div><div class="v">${fmtInt(v.c1700.votes)}</div><div class="s">${pct(v.c1700.votes / total, 3)} dos votos · ${fmtInt(v.c1700.urnas_with_late)} urnas</div></div>
    <div class="tile"><div class="k">Depois das 17:10 (fim das filas normais)</div><div class="v">${fmtInt(v.c1710.votes)}</div><div class="s">${pct(v.c1710.votes / total, 4)} dos votos · ${fmtInt(v.c1710.urnas_with_late)} urnas</div></div>
    <div class="tile"><div class="k">Urnas abertas até 18:55 ou mais</div><div class="v">${fmtInt(D.urnas)}</div><div class="s">${fmtInt(D.no_vote_after_1700)} não receberam nenhum voto depois das 17:00</div></div>
    <div class="tile"><div class="k">Efeito máximo possível na diferença</div><div class="v">${fmtInt(maxShift)}</div><div class="s">${pct(maxShift / Math.abs(n0.margin), 2)} da diferença final</div></div>
  </div>`);

  // minute by minute
  sections.push(`<h2>Minuto a minuto</h2><p class="lede">Às 17:00 todas as urnas ainda estavam abertas; às 17:01, ${fmtInt(E.open_at_1701.urnas)}; às 17:10, ${fmtInt(E.minute_series.open_urnas[70])}. Cerca de ${fmtInt(E.minute_series.open_urnas[120])} urnas seguiram abertas das 17:30 até perto das 19:00 — é a "prorrogação". Nesse período, os votos foram poucos: os gráficos abaixo mostram por quê.</p>
    <div class="chart-title">Votos registrados por minuto no Brasil, 16:00–20:00</div><div class="chart" id="ch-min-all"></div>
    <div class="chart-title">Zoom: votos por minuto no Brasil depois das 17:10 — o período da prorrogação (17:10–19:30, escala própria)</div><div class="chart" id="ch-min-zoom"></div>
    <div class="chart-title">Votos por minuto nas ${fmtInt(D.urnas)} urnas que ficaram abertas até 18:55 ou mais</div><div class="chart" id="ch-min-d"></div>
    <div class="chart-title">Urnas ainda abertas, por minuto</div><div class="chart" id="ch-open"></div>
    <p class="note">${(() => { const ms = E.minute_series.D, d = ms.bio.map((x, i) => x + ms.failed[i] + ms.noask[i]);
      const w = d.slice(90, 175), tot = w.reduce((a, b) => a + b, 0), per10 = []; for (let i = 70; i < 190; i += 10) per10.push([i, d.slice(i, i + 10).reduce((a, b) => a + b, 0)]);
      const pk = per10.reduce((a, b) => (b[1] > a[1] ? b : a));
      return `Entre 17:30 e 18:55, as ${fmtInt(D.urnas)} urnas do grupo D receberam juntas ${fmtInt(tot)} votos — em média ${(tot / 85).toFixed(0)} por minuto no país inteiro, cerca de ${(tot / D.urnas / (85 / 60)).toFixed(2).replace('.', ',')} voto por urna por hora. O maior intervalo de 10 minutos foi ${hhmm(t0 + pk[0] * 60)}–${hhmm(t0 + (pk[0] + 10) * 60)}, com ${fmtInt(pk[1])} votos. `; })()}Nas urnas que ficaram até 18:55 ou mais, o último voto foi, na mediana, às ${hhmm(D.last_vote_quantiles['0.5'])}; ${pct(D.share_last_vote_before_1710, 0)} delas não receberam nenhum voto depois das 17:10. No total, receberam ${fmtInt(D.after_1700)} votos depois das 17:00 (${pct(D.after_1700 / D.votes, 2)} dos seus votos), ${fmtInt(D.after_1800)} depois das 18:00 e ${fmtInt(D.after_1900)} depois das 19:00.</p>`);

  // hard stop table
  const rows = E.cutoffs.map(k => {
    const b = n[k.key];
    return `<tr><td>${k.label}</td><td>${fmtInt(b.late_votes)}</td><td>${pct(b.late_votes / total, 3)}</td><td>${signed(b.margin_min)} a ${signed(b.margin_max)}</td><td>${sh(b.lula_share_min, 2)} a ${sh(b.lula_share_max, 2)}</td><td>${b.winner_can_change ? '<span class="yes">sim</span>' : '<span class="no">não</span>'}</td><td>${statesChange(k.key)}</td><td>${E.muni_flips[k.key].munis_flip_possible}${E.muni_flips[k.key].munis_tie_possible ? ` (+${E.muni_flips[k.key].munis_tie_possible} empate)` : ''}</td></tr>`;
  }).join('');
  sections.push(`<h2>Se a votação parasse em cada horário</h2><p class="lede">Para cada horário de corte: quantos votos vieram depois, e a faixa <b>exata</b> do resultado se esses votos não existissem. O limite de um lado supõe que todos eram de ${esc(L.short)}; o do outro, que todos eram de ${esc(F.short)} — nunca mais votos do que o candidato teve em cada urna. Não há hipótese sobre como votaram.</p>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Corte</th><th>Votos depois</th><th>% dos votos</th><th>Diferença ${esc(L.short)} − ${esc(F.short)} possível</th><th>${esc(L.short)} % dos válidos possível</th><th>Vencedor nacional muda?</th><th>Estados que mudam</th><th>Municípios que mudam</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note">Resultado oficial: ${esc(L.name)} ${fmtInt(n0.lula)} (${sh(n0.lula_share, 2)}), ${esc(F.name)} ${fmtInt(n0.flavio)}. Inclui o exterior, onde não houve prorrogação (todas as urnas encerraram até 18:15 no horário local). Votos sem horário no log (${fmtInt(E.totals.unknown_time_votes)}, de 4 urnas) entram como se pudessem ser depois do corte. Num cenário ainda mais extremo — todos os votos do exterior removidos como se fossem de ${esc(L.short)}, além dos votos depois das 17:00 — a diferença ficaria em ${signed(E.national_abroad_also_removable.margin_min)}.</p>
    ${flip0.list.length ? `<div class="fact"><b>Municípios no limite:</b> ${flip0.list.map(x => `${esc(x.muni)} (${esc(x.uf)}): ${esc(L.short)} ${fmtInt(x.lula)} × ${fmtInt(x.flavio)} ${esc(F.short)}, ${fmtInt(x.late_votes)} voto(s) depois das 17:00 — diferença possível de ${signed(x.margin_min)} a ${signed(x.margin_max)}`).join('; ')}.</div>` : ''}`);

  // where
  const g = E.groups.map(x => `<tr><td><b>${x.group}</b> · ${esc(x.label)}</td><td>${fmtInt(x.urnas)}</td><td>${pct(x.share_urnas, 1)}</td><td>${fmtInt(x.after_c1700)}</td><td>${fmtInt(x.after_c1710)}</td><td>${sh(x.lula_share)}</td></tr>`).join('');
  const reg2 = E.regions.map(x => `<tr><td>${esc(x.region)}</td><td>${fmtInt(x.urnas)}</td><td>${fmtInt(x.group_D)}</td><td>${fmtInt(x.after_c1700)}</td><td>${fmtInt(x.after_c1710)}</td><td>${fmtInt(x.after_c1800)}</td><td>${sh(x.lula_share)}</td></tr>`).join('');
  const st = [...E.states].sort((a, b) => b.group_D - a.group_D || b.bounds.c1700.late_votes - a.bounds.c1700.late_votes).map(x => {
    const b = x.bounds.c1700;
    return `<tr><td>${esc(x.uf)}</td><td>${fmtInt(x.urnas)}</td><td>${fmtInt(x.group_D)}</td><td>${pct(x.share_D, 1)}</td><td>${fmtInt(b.late_votes)}</td><td>${fmtInt(x.bounds.c1710.late_votes)}</td><td>${sh(x.lula_share)}</td><td>${x.lula_share_D == null ? '—' : sh(x.lula_share_D)}</td><td>${signed(b.margin)}</td><td>${signed(b.margin_min)} a ${signed(b.margin_max)}</td><td>${b.winner_can_change ? '<span class="yes">sim</span>' : 'não'}</td></tr>`;
  }).join('');
  const tm = E.top_munis_D.slice(0, 15).map(x => `<tr><td>${esc(x.muni)} (${esc(x.uf)})</td><td>${fmtInt(x.urnas)}</td><td>${fmtInt(x.D)}</td><td>${fmtInt(x.after_1700)}</td><td>${fmtInt(x.after_1710)}</td><td>${sh(x.lula_share)}</td></tr>`).join('');
  const sp = E.regions.find(r => r.region === 'Sudeste'), ne = E.regions.find(r => r.region === 'Nordeste');
  sections.push(`<h2>Onde ficaram as urnas abertas</h2><p class="lede">As urnas foram agrupadas pelo horário de encerramento registrado no BU. O grupo D — encerradas a partir de 18:55 — é o das urnas que ficaram abertas cerca de duas horas a mais. ${fmtInt(sp.group_D)} delas (${pct(sp.group_D / D.urnas, 0)}) estavam no Sudeste e ${fmtInt(ne.group_D)} (${pct(ne.group_D / D.urnas, 0)}) no Nordeste. Dentro de cada estado, ficaram sobretudo nas capitais e grandes cidades: ${fmtInt(E.group_D_lean.in_lula_majority_munis)} das ${fmtInt(D.urnas)} em municípios onde ${esc(L.short)} venceu; no conjunto, essas urnas deram ${sh(E.group_D_lean.lula_share_D_urnas)} a ${esc(L.short)} (Brasil: ${sh(E.group_D_lean.lula_share_brazil)}). Esses percentuais incluem todos os votos dessas urnas, a maioria dados antes das 17:00.</p>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Grupo</th><th>Urnas</th><th>% das urnas</th><th>Votos depois das 17:00</th><th>Depois das 17:10</th><th>${esc(L.short)} % (todas as urnas do grupo)</th></tr></thead><tbody>${g}</tbody></table></div>
    <div class="chart-title">Por região</div>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Região</th><th>Urnas</th><th>Grupo D</th><th>Votos depois das 17:00</th><th>Depois das 17:10</th><th>Depois das 18:00</th><th>${esc(L.short)} % (região)</th></tr></thead><tbody>${reg2}</tbody></table></div>
    <div class="chart-title">Por estado (ordenado pelo grupo D)</div>
    <div class="table-wrap"><table class="grid"><thead><tr><th>UF</th><th>Urnas</th><th>Grupo D</th><th>% D</th><th>Votos após 17:00</th><th>Após 17:10</th><th>${esc(L.short)} % estado</th><th>${esc(L.short)} % urnas D</th><th>Diferença oficial</th><th>Parada às 17:00: faixa</th><th>Muda?</th></tr></thead><tbody>${st}</tbody></table></div>
    <div class="chart-title">Municípios com mais urnas no grupo D</div>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Município</th><th>Urnas</th><th>Grupo D</th><th>Votos após 17:00</th><th>Após 17:10</th><th>${esc(L.short)} % município</th></tr></thead><tbody>${tm}</tbody></table></div>`);

  // biometrics
  const bioRow = (label, b) => `<tr><td>${label}</td><td>${sh(b.sem_biometria.after, 1)}</td><td>${sh(b.sem_biometria.before, 1)}</td><td>${pp(b.sem_biometria.diff_pp)}</td><td>${sh(b.failed.after, 1)} / ${sh(b.failed.before, 1)}</td><td>${sh(b.noask.after, 1)} / ${sh(b.noask.before, 1)}</td><td>${fmtInt(b.sem_biometria.after_n)}</td></tr>`;
  const B = E.biometrics;
  sections.push(`<h2>Quem votou depois das 17:00: biometria</h2><p class="lede"><b>Sem biometria</b> = leitura da digital falhou e o mesário liberou o eleitor, <b>mais</b> eleitores para quem a urna não pediu a digital. A referência é a última hora regular (16:00–17:00) <b>nas mesmas urnas</b>, para comparar eleitores de fim de dia com eleitores de fim de dia.</p>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Recorte</th><th>Sem biometria depois</th><th>16:00–17:00</th><th>Diferença</th><th>Falha na leitura (depois / ref.)</th><th>Não pedida (depois / ref.)</th><th>Votos depois</th></tr></thead><tbody>
      ${bioRow('Todas as urnas, depois das 17:00', B.all_urnas.c1700)}${bioRow('Todas as urnas, depois das 17:10', B.all_urnas.c1710)}${bioRow('Todas as urnas, depois das 18:00', B.all_urnas.c1800)}
      ${bioRow('Grupo D, depois das 17:00', B.group_D.c1700)}${bioRow('Grupo D, depois das 17:10', B.group_D.c1710)}${bioRow('Grupo D, depois das 18:00', B.group_D.c1800)}
    </tbody></table></div>
    <p class="note">A diferença em todas as urnas logo depois das 17:00 vem da fila de encerramento (17:00–17:10): mais falhas de leitura da digital. Depois das 17:10 — e nas urnas da prorrogação em qualquer corte — a proporção de votos sem biometria é a mesma da última hora regular. Votos "rápidos" (falha na leitura, liberação e voto em poucos segundos) depois das 17:00: ${fmtInt(E.volume.c1700.fast)}.</p>`);

  // estimates
  const ci = a => `${(a[0] * 100).toFixed(1).replace('.', ',')}% a ${(a[1] * 100).toFixed(1).replace('.', ',')}%`;
  sections.push(`<h2>Em quem votaram os eleitores depois das 17:00? (estimativas)</h2>
    <div class="caveat">As linhas abaixo <b>não são contagens</b>: são comparações estatísticas entre urnas, porque o voto de cada eleitor não fica ligado ao horário. Servem para testar hipóteses como "os votos depois das 17:00 foram 80% de ${esc(L.short)}".</div>
    <ul class="plain">
      <li><b>Inclinação dos lugares:</b> se cada eleitor tardio tivesse votado como o restante da própria urna, os votos depois das 17:00 teriam sido ${sh(E.lean_if_like_their_urna.c1700.lula_share)} ${esc(L.short)} (depois das 17:10: ${sh(E.lean_if_like_their_urna.c1710.lula_share)}). Isso descreve onde houve voto tardio, não como esses eleitores votaram.</li>
      <li><b>Dentro do mesmo local de votação</b> (${fmtInt(reg.places)} locais): comparando urnas com mais e menos votos depois das 17:00, a fatia de ${esc(L.short)} entre os eleitores tardios é estimada em <b>${sh(reg.implied_late_lula_share)}</b> (intervalo de 95%: ${ci(reg.implied_late_ci)}), contra ${sh(reg.baseline_identifying_places)} entre os demais eleitores desses locais. A hipótese "80% ${esc(L.short)}" fica ${Math.abs(reg.z_vs_80pct).toFixed(1).replace('.', ',')} erros-padrão abaixo do observado e é rejeitada; "65%", a ${Math.abs(reg.z_vs_65pct).toFixed(1).replace('.', ',')} erros-padrão. Conferências: sem pesos, ${pp(reg.beta_unweighted * 100)}; com os horários embaralhados dentro de cada local (placebo), ${pp(reg.placebo_mean * 100)} ± ${(reg.placebo_sd * 100).toFixed(1).replace('.', ',')}.</li>
      <li><b>Depois das 17:10</b> há só ${fmtInt(n10.late_votes)} votos: poucos demais para estimar em quem votaram (intervalo de 95% da mesma estimativa: ${ci(E.place_regression.c1710.implied_late_ci)}). Para eles vale a conta exata: no máximo ${fmtInt(Math.max(n10.max_lula_removed, n10.max_flavio_removed))} votos de diferença.</li>
      ${sib ? `<li><b>Vizinhas de urna:</b> em ${fmtInt(sib.places)} locais com urnas da prorrogação e urnas que fecharam no horário, as da prorrogação deram ${pp(sib.mean_diff_pp, 2)} a ${esc(L.short)} em relação às vizinhas (intervalo de 95%: ${pp(sib.ci_pp[0], 2)} a ${pp(sib.ci_pp[1], 2)}); comparecimento ${pp(sib.turnout_diff_pp, 2)}.</li>` : ''}
    </ul>`);

  // top urnas, data quality, method
  const tu = E.top_urnas_after_1710.slice(0, 20).map(x => `<tr><td>${esc(x.muni)} (${esc(x.uf)})</td><td>${x.zona}/${x.secao}</td><td>${hhmmss(x.close)}</td><td>${fmtInt(x.comp)}</td><td>${fmtInt(x.after_1700)}</td><td>${fmtInt(x.after_1710)}</td><td>${fmtInt(x.after_1800)}</td><td>${sh(x.lula_share)}</td></tr>`).join('');
  const q = E.data_quality;
  sections.push(`<h2>Urnas com mais votos depois das 17:10</h2>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Município</th><th>Zona/Seção</th><th>Encerrou</th><th>Votos</th><th>Após 17:00</th><th>Após 17:10</th><th>Após 18:00</th><th>${esc(L.short)} % (urna inteira)</th></tr></thead><tbody>${tu}</tbody></table></div>
    <h2>Qualidade dos dados e método</h2>
    <ul class="plain">
      <li>Totais conferem com o resultado oficial: ${esc(L.name)} ${fmtInt(n0.lula)}, ${esc(F.name)} ${fmtInt(n0.flavio)}, ${fmtInt(E.totals.votes_bu + (M.states.find(s => s.uf === 'ZZ') ? 0 : 0))} votos no Brasil.</li>
      <li>${esc(M.validation)}</li>
      <li>Urnas com voto registrado mais de 1 minuto depois do próprio encerramento: ${fmtInt(q.votes_after_own_close)}. Urnas com voto antes das 08:00: ${fmtInt(q.first_vote_before_0800)}. A urna que encerrou por último (${esc(q.latest_closings[0].muni)}, ${hhmmss(q.latest_closings[0].close)}) teve o último voto às ${hhmmss(q.latest_closings[0].last_vote)}.</li>
      <li>Os relógios das urnas estão no horário local; o fuso de cada município foi deduzido do horário de abertura no BU (todas abrem às 08:00 de Brasília). Os horários de corte são de Brasília.</li>
      <li>Grupos por horário de encerramento (BU): A até 17:01; B 17:01–17:10; C 17:10–18:55; D a partir de 18:55.</li>
      <li>Dados desta página: <a href="data/extension.json.gz">data/extension.json.gz</a>. Código: <code>pipeline/late_votes_table.py</code> e <code>pipeline/analyze_extension.py</code>.</li>
    </ul>`);

  document.getElementById('report').innerHTML = sections.join('');
  const ms = E.minute_series;
  const upto = 240;   // 16:00–20:00
  const sum = s => s.bio.map((x, i) => x + s.failed[i] + s.noask[i]).slice(0, Math.max(upto, 210));
  areaChart(document.getElementById('ch-min-all'), { series: sum(ms.all).slice(0, upto), t0, step: 60, cursor: 17 * 3600, color: '#1baf7a', label: 'Votos' });
  areaChart(document.getElementById('ch-min-zoom'), { series: sum(ms.all).slice(70, 210), t0: t0 + 70 * 60, step: 60, cursor: 19 * 3600, color: '#1baf7a', label: 'Votos' });
  areaChart(document.getElementById('ch-min-d'), { series: sum(ms.D).slice(0, upto), t0, step: 60, cursor: 17 * 3600, color: '#1baf7a', label: 'Votos (grupo D)' });
  areaChart(document.getElementById('ch-open'), { series: ms.open_urnas.slice(0, upto), t0, step: 60, cursor: 17 * 3600, color: '#9a9890', label: 'Urnas abertas', unit: 'urnas' });
}

main().catch(e => { document.getElementById('report').innerHTML = `<div class="empty">Falha ao carregar: ${esc(e.message)}</div>`; console.error(e); });
