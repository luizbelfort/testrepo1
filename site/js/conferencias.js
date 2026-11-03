// "Conferências das urnas": per-urna verification of the TSE files and neutral statistical signals.
// Every number comes from data/conferencias.json.gz (pipeline/verify_urnas.py, anomaly_scan.py, summarize_checks.py).
import { getJSON, setDataVersion } from './data.js?v=20261103h';
import { fmtInt, pct } from './scales.js?v=20261103h';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (x, d = 2) => (x == null ? '—' : Number(x).toFixed(d).replace('.', ','));
const pv = p => (p == null ? '—' : p < 1e-12 ? '< 1e-12' : p.toExponential(1).replace('.', ','));

function verifySection(C, M) {
  const N = C.verify_national;
  if (!N) return '<h2>Conferência dos arquivos</h2><p class="lede">Conferência em andamento.</p>';
  const rows = C.checks.map(c => {
    const ok = N[c.key], bad = N.urnas - ok;
    return `<tr><td>${esc(c.label)}</td><td>${fmtInt(ok)}</td><td>${bad ? `<span class="yes">${fmtInt(bad)}</span>` : '0'}</td><td>${pct(ok / N.urnas, 3)}</td></tr>`;
  }).join('');
  const st = C.verify_states.map(s => {
    const bad = C.checks.reduce((a, c) => a + (s.urnas - s[c.key] > 0 ? 1 : 0), 0);
    const worst = C.checks.filter(c => s.urnas - s[c.key] > 0).map(c => `${c.key}: ${fmtInt(s.urnas - s[c.key])}`).join(' · ');
    return `<tr><td>${esc(s.scope)}</td><td>${fmtInt(s.urnas)}</td><td>${bad ? `<span class="yes">${esc(worst)}</span>` : 'todas conferem'}</td></tr>`;
  }).join('');
  const fl = (C.verify_fail_list || []).slice(0, 200).map(r => `<tr><td>${esc(r.uf)}</td><td>${esc(r.muni)}</td><td><code>${esc(r.key)}</code></td><td>${esc(r.failed_checks)}</td><td>${r.bu_lula ?? '—'} / ${r.rdv_lula ?? '—'} / ${r.w_lula ?? '—'}</td><td>${r.bu_flavio ?? '—'} / ${r.rdv_flavio ?? '—'} / ${r.w_flavio ?? '—'}</td><td>${r.bu_comp ?? '—'} / ${r.rdv_n ?? '—'} / ${r.w_comp ?? '—'}</td><td>${esc(r.fetch_error || r.sig_error || r.bu_error || r.rdv_error || r.sw_mismatch || r.hw_mismatch || '')}</td></tr>`).join('');
  const iss = Object.entries(C.cert_issuers || {}).map(([k, v]) => `${esc(k)}: ${fmtInt(v)}`).join(' · ');
  const mod = Object.entries(C.models || {}).map(([k, v]) => `${k === '—' ? 'sem modelo (SA)' : 'UE20' + parseInt(k)}: ${fmtInt(v)}`).join(' · ');
  return `
  <h2>Conferência dos arquivos de cada urna</h2>
  <p class="lede">Para cada uma das ${fmtInt(N.urnas)} urnas, foram baixados do TSE os arquivos que ela gerou e transmitiu — Boletim de Urna (BU), Registro Digital do Voto (RDV), imagem do BU, log e o arquivo de assinaturas — e conferidos entre si e com a planilha de resultados por seção (bweb). Uma linha com zero na coluna "não confere" significa que <b>todas</b> as urnas passaram naquela conferência.</p>
  <div class="table-wrap"><table class="grid"><thead><tr><th>Conferência</th><th>Confere</th><th>Não confere</th><th>% que confere</th></tr></thead><tbody>${rows}</tbody></table></div>
  <p class="note">Certificados das urnas, por autoridade emissora: ${iss}. Modelos: ${mod}.</p>
  ${C.hab_not_applicable ? `<p class="note">A conferência das habilitações não se aplica a ${fmtInt(C.hab_not_applicable)} urnas do exterior: o BU dessas urnas não traz a contagem por tipo de habilitação (não há biometria no exterior). Elas aparecem como "confere" nessa linha.</p>` : ''}
  ${(C.sa_urnas || []).length ? `<p class="note">${fmtInt(C.sa_urnas.length)} seções foram apuradas pelo Sistema de Apuração (SA, contingência — arquivos <code>busa.dat</code>/<code>sa.vsc</code> em vez dos de uma urna) e ficam fora da tabela acima, porque não têm os arquivos de urna a conferir: ${C.sa_urnas.map(r => `<code>${esc(r.key)}</code>`).join(', ')}.</p>` : ''}
  <div class="caveat"><b>O que não foi possível conferir, e por quê:</b>
    <ul class="plain">
      <li>O <b>valor</b> das assinaturas digitais. A assinatura de software usa o algoritmo CEPESC, de uso restrito do governo; a da urna usa uma curva elíptica de 521 bits (formato Ed521) cujo procedimento exato o TSE não publica — os formatos documentados publicamente foram testados e nenhum corresponde. O que foi conferido: que cada arquivo publicado tem exatamente o hash SHA-512 registrado e assinado pela urna, que a lista assinada não foi alterada (auto-hash), e que o certificado pertence àquela urna e era válido no dia.</li>
      <li>Arquivos assinados pela urna que o TSE não publica no pacote (${esc(C.unpublished_signed_files || '')}).</li>
      <li>Em 2026 o formato do BU e do RDV mudou em relação à especificação publicada pelo TSE (campos novos e a assinatura das tuplas do BU, antes Ed25519, agora em outro formato não documentado). Os campos de votos foram identificados pela estrutura e conferidos contra o RDV e a planilha bweb; as especificações adaptadas estão em <code>pipeline/spec/</code>.</li>
    </ul></div>
  <div class="chart-title">Por estado</div>
  <div class="table-wrap"><table class="grid"><thead><tr><th>UF</th><th>Urnas</th><th>Divergências</th></tr></thead><tbody>${st}</tbody></table></div>
  <div class="chart-title">Urnas com alguma conferência que não fechou (${fmtInt(C.verify_fail_total || 0)}) — <a href="data/conferencias/conferencia_falhas.csv" download>baixar CSV completo</a> · <a href="data/conferencias/conferencia_por_urna.csv.gz" download>todas as urnas</a></div>
  ${fl ? `<div class="table-wrap"><table class="grid"><thead><tr><th>UF</th><th>Município</th><th>Arquivo</th><th>Conferências que falharam</th><th>Lula BU/RDV/bweb</th><th>Flávio BU/RDV/bweb</th><th>Total BU/RDV/bweb</th><th>Detalhe</th></tr></thead><tbody>${fl}</tbody></table></div>` : '<p class="note">Nenhuma.</p>'}`;
}

function anomalySection(C, M) {
  const A = C.anomaly;
  if (!A) return '<h2>Sinais estatísticos</h2><p class="lede">Varredura em andamento.</p>';
  const c = M.election.candidates, L = c[0], F = c[1];
  const tot = A.totals;
  const flags = A.flags.map(f => `<tr><td>${esc(f.label)}</td><td>${fmtInt(f.urnas)}</td><td>${pct(f.urnas / A.urnas_scanned, 2)}</td><td>${fmtInt(f.lula_won)}</td><td>${fmtInt(f.flavio_won)}</td><td>${f.lula_share == null ? '—' : pct(f.lula_share, 1)}</td><td><a href="data/conferencias/sinal_${f.key}.csv" download>CSV</a></td></tr>`).join('');
  const cr = A.corr_within_muni;
  const lists = A.flags.filter(f => f.urnas).map(f => `
    <details><summary>${esc(f.label)} — ${fmtInt(f.urnas)} urnas (maiores 50 por número de votos)</summary>
    <div class="table-wrap"><table class="grid"><thead><tr><th>UF</th><th>Município</th><th>Zona</th><th>Seção</th><th>Votos</th><th>Falha digital</th><th>Taxa / município</th><th>p</th><th>Maior sequência</th><th>Rápidos</th><th>Não cadastr.</th><th>Comparec.</th><th>${esc(L.short)}</th><th>${esc(F.short)}</th></tr></thead><tbody>
    ${f.rows.slice(0, 50).map(r => `<tr><td>${esc(r.uf)}</td><td>${esc(r.muni)}</td><td>${r.zona}</td><td>${r.secao}</td><td>${fmtInt(r.n)}</td><td>${fmtInt(r.failed)}</td><td>${pct(r.failed_rate, 0)} / ${pct(r.mun_failed_rate, 0)}</td><td>${pv(r.p_failed_high)}</td><td>${r.run_failed}</td><td>${r.fast}</td><td>${r.unreg}</td><td>${pct(r.turnout, 1)}</td><td>${fmtInt(r.lula)}</td><td>${fmtInt(r.flavio)}</td></tr>`).join('')}
    </tbody></table></div></details>`).join('');
  const models = A.by_model.map(m => `<tr><td>${esc(m.model)}</td><td>${fmtInt(m.urnas)}</td><td>${pct(m.failed_rate, 1)}</td><td>${pct(m.noask_rate, 1)}</td><td>${pct(m.lula_share, 1)}</td></tr>`).join('');
  return `
  <h2>Sinais estatísticos em cada urna</h2>
  <p class="lede">Cada urna foi comparada com as demais do <b>mesmo município</b>, a partir do log (eleitor a eleitor). Os critérios estão abaixo e são fixos para todos; os limiares de probabilidade (1 em 10 milhões) levam em conta que são quase meio milhão de urnas testadas. Um sinal é um padrão incomum que merece ser olhado — <b>não é prova de nada</b>: urna com leitor de digital ruim, seção com muitos idosos ou trabalhadores manuais, fila no fim do dia e erros de cadastro produzem os mesmos padrões.</p>
  <div class="tiles">
    <div class="tile"><div class="k">Eleitores analisados no log</div><div class="v">${fmtInt(A.votes_scanned)}</div><div class="s">${fmtInt(A.urnas_scanned)} urnas</div></div>
    <div class="tile"><div class="k">Digital falhou, mesário liberou</div><div class="v">${fmtInt(tot.failed)}</div><div class="s">${pct(tot.failed / A.votes_scanned, 1)} dos eleitores</div></div>
    <div class="tile"><div class="k">Urna não pediu a digital</div><div class="v">${fmtInt(tot.noask)}</div><div class="s">${pct(tot.noask / A.votes_scanned, 1)} dos eleitores</div></div>
    <div class="tile"><div class="k">Urnas com algum sinal</div><div class="v">${fmtInt(A.any_flag_urnas)}</div><div class="s">${pct(A.any_flag_urnas / A.urnas_scanned, 2)} das urnas · ${esc(L.short)} ${pct(A.any_flag_lula_share, 1)} nelas (Brasil ${pct(A.lula_share_all, 1)})</div></div>
  </div>
  <div class="table-wrap"><table class="grid"><thead><tr><th>Sinal</th><th>Urnas</th><th>% das urnas</th><th>${esc(L.short)} venceu</th><th>${esc(F.short)} venceu</th><th>${esc(L.short)} % dos válidos nelas</th><th>Lista</th></tr></thead><tbody>${flags}</tbody></table></div>
  <p class="note">Referência: no Brasil, ${esc(L.short)} venceu em ${fmtInt(A.lula_won_all)} urnas e ${esc(F.short)} em ${fmtInt(A.flavio_won_all)}. Se um sinal aparecesse muito mais em urnas de um candidato do que essa proporção, seria um indício a investigar; a coluna "% dos válidos" permite comparar.</p>
  <div class="fact"><b>Correlação dentro do município</b> (cada urna comparada com a média do seu município, ponderada pelo número de eleitores; −1 a +1, 0 = nenhuma relação):
    falha de leitura × votos em ${esc(L.short)}: <b>${num(cr.failed_rate_vs_lula_share, 3)}</b> ·
    urna não pediu digital × votos em ${esc(L.short)}: <b>${num(cr.noask_rate_vs_lula_share, 3)}</b> ·
    votos rápidos × votos em ${esc(L.short)}: <b>${num(cr.fast_rate_vs_lula_share, 3)}</b> ·
    falha de leitura × comparecimento: <b>${num(cr.failed_rate_vs_turnout, 3)}</b>.
    Valor positivo = urnas com mais daquele padrão deram, em média, um pouco mais votos a ${esc(L.short)} do que as vizinhas; negativo, a ${esc(F.short)}. Correlação não indica causa (o perfil do eleitorado da seção afeta as duas coisas).</div>
  <div class="chart-title">Por modelo de urna</div>
  <div class="table-wrap"><table class="grid"><thead><tr><th>Modelo</th><th>Urnas</th><th>Digital falhou</th><th>Não pediu digital</th><th>${esc(L.short)} %</th></tr></thead><tbody>${models}</tbody></table></div>
  <div class="chart-title">Listas</div>${lists}
  <div class="caveat"><b>Definições.</b> <i>Falha de leitura</i>: o log registra a tentativa de digital e, em seguida, a liberação manual pelo mesário. <i>Sequência</i>: eleitores consecutivos todos com falha; a probabilidade é a de uma sequência tão longa surgir ao acaso com a taxa de falha da própria urna. <i>Voto rápido</i>: falha de leitura, fase da digital ≤ 30 s, liberação ≤ 10 s e voto ≤ 5 s. <i>Digital não cadastrada</i>: a liberação manual foi confirmada com uma digital que a urna não reconhece como do mesário cadastrado (o log não identifica a pessoa). <i>Comparecimento</i>: eleitores que votaram ÷ aptos, comparado com as demais urnas do município.</div>`;
}

async function main() {
  const M = await getJSON('data/manifest.json');
  setDataVersion(M.generated);
  const C = await getJSON('data/conferencias.json.gz');
  const N = C.verify_national;
  const intro = `
  <h1>Conferências das urnas</h1>
  <p class="lede">Duas perguntas, urna por urna, em todo o Brasil: <b>os arquivos publicados pelo TSE batem entre si e com as assinaturas da urna?</b> E <b>há urnas com padrões estatísticos fora do comum</b> — falhas de biometria, sequências, votos rápidos, comparecimento? Os dados são mostrados como estão; os critérios são os mesmos para todas as urnas e todos os candidatos.</p>
  ${N ? `<div class="answer">${fmtInt(N.urnas)} urnas conferidas. Hashes assinados pela urna conferem em <b>${fmtInt(N.hw_hashes)}</b>; RDV = BU em <b>${fmtInt(N.bu_rdv)}</b>; BU = planilha oficial em <b>${fmtInt(N.bu_bweb)}</b>.${C.verify_fail_total ? ` ${fmtInt(C.verify_fail_total)} urnas têm ao menos uma conferência que não fechou — todas listadas abaixo, com o motivo.` : ''}</div>` : ''}`;
  document.getElementById('report').innerHTML = intro + verifySection(C, M) + anomalySection(C, M) +
    `<p class="note">Código: <code>pipeline/verify_urnas.py</code>, <code>pipeline/anomaly_scan.py</code>, <code>pipeline/summarize_checks.py</code>. Fonte: arquivos "bu_imgbu_logjez_rdv_vscmr" e "bweb" do 2º turno, cdn.tse.jus.br.</p>`;
}
main().catch(e => { document.getElementById('report').innerHTML = `<div class="empty">Erro ao carregar: ${esc(e.message)}</div>`; });
