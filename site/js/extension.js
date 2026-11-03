// "Prorrogação" view: what happened after 17:00, and the exact limits of its effect on the result.
// Data: data/extension.json.gz (pipeline/analyze_extension.py). Nothing here infers the candidate of a vote:
// the urna log does not record it. Bounds assume the most extreme possible composition in each direction.
import { fmtInt, pct, hhmm, hhmmss } from './scales.js?v=20261103f';

export let EXT = null;
const munIdx = new Map();   // uf -> Map(ibge -> row in EXT.munis[uf])

export async function loadExtension(getJSON) {
  EXT = await getJSON('data/extension.json.gz');
  for (const [uf, r] of Object.entries(EXT.munis)) munIdx.set(uf, new Map(r.ibge.map((id, i) => [id, i])));
  return EXT;
}

export function cutFor(t) {
  const cs = EXT.cutoffs; let c = cs[0];
  for (const x of cs) if (x.t <= t) c = x;
  return c;
}

// Sum the per-municipality aggregates over a scope. All fields are additive (bounds are sums of per-urna minima).
function sumMunis(uf, ibges, cut) {
  const r = EXT.munis[uf]; if (!r) return null;
  const idx = munIdx.get(uf), s = { late: 0, semBio: 0, a: 0, b: 0, h16: 0, h16SemBio: 0, comp: 0, lula: 0, flavio: 0, D: 0, C: 0, unknown: 0 };
  for (const id of ibges) {
    const i = idx.get(id); if (i == null) continue;
    s.late += r[`${cut}_all`][i]; s.semBio += r[`${cut}_sem_bio`][i]; s.a += r[`${cut}_max_lula`][i]; s.b += r[`${cut}_max_flavio`][i];
    s.h16 += r.h16_all[i]; s.h16SemBio += r.h16_sem_bio[i]; s.comp += r.comp[i]; s.lula += r.lula[i]; s.flavio += r.flavio[i];
    s.D += r.group_D[i]; s.C += r.group_C[i]; s.unknown += r.unknown[i];
  }
  return s;
}

export function scopeAgg(ufs, ibgesOf, cut, abroad) {
  const tot = { late: 0, semBio: 0, a: 0, b: 0, h16: 0, h16SemBio: 0, comp: 0, lula: 0, flavio: 0, D: 0, C: 0, unknown: 0 };
  for (const uf of ufs) {
    if (uf === 'ZZ') continue;
    const s = sumMunis(uf, ibgesOf(uf), cut); if (!s) continue;
    for (const k in tot) tot[k] += s[k];
  }
  if (abroad) { tot.lula += EXT.totals.lula_abroad; tot.flavio += EXT.totals.flavio_abroad; }   // unaffected by the extension
  const M = tot.lula - tot.flavio, any = tot.late + tot.unknown > 0;
  return { ...tot, margin: M, marginMin: M - tot.a, marginMax: M + tot.b,
    share: tot.lula / (tot.lula + tot.flavio), shareMin: (tot.lula - tot.a) / (tot.lula - tot.a + tot.flavio),
    shareMax: tot.lula / (tot.lula + tot.flavio - tot.b),
    // a hard stop only matters where votes were cast after the cutoff
    canChange: any && ((M > 0 && M - tot.a < 0) || (M < 0 && M + tot.b > 0) || (M === 0 && (tot.a > 0 || tot.b > 0))),
    tiePossible: any && ((M > 0 && M - tot.a <= 0) || (M < 0 && M + tot.b >= 0)) };
}

export function muniLate(uf, ibge, cut) {
  const r = EXT?.munis[uf]; if (!r) return null;
  const i = munIdx.get(uf).get(ibge); if (i == null) return null;
  const late = r[`${cut}_all`][i] + r.unknown[i], comp = r.comp[i];
  const M = r.lula[i] - r.flavio[i], a = r[`${cut}_max_lula`][i], b = r[`${cut}_max_flavio`][i];
  const flip = late > 0 && ((M > 0 && M - a <= 0) || (M < 0 && M + b >= 0) || (M === 0 && (a > 0 || b > 0)));   // flip or tie possible
  return { late, comp, per: comp ? late / comp : null, flip, semBio: r[`${cut}_sem_bio`][i], D: r.group_D[i] };
}

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const signed = n => (n > 0 ? '+' : n < 0 ? '−' : '') + fmtInt(Math.abs(n));

export function cutButtons(cur) {
  return `<div class="seg ext-cuts" role="group" aria-label="Horário de corte">${EXT.cutoffs.map(c =>
    `<button type="button" data-cut-t="${c.t}" class="${c.key === cur.key ? 'on' : ''}">${c.label}</button>`).join('')}</div>`;
}

export function extCards(a, cut, title, scopeLevel, cand) {
  const winner = a.margin > 0 ? cand[0].name : a.margin < 0 ? cand[1].name : 'empate';
  const late = a.late + a.unknown;
  const verdict = a.canChange
    ? `<div class="verdict warn"><b>O vencedor poderia mudar</b> neste recorte se todos os votos depois das ${cut.label} fossem de um só candidato.</div>`
    : a.tiePossible
      ? `<div class="verdict warn"><b>O resultado poderia terminar empatado</b> neste recorte, no caso extremo de todos os ${fmtInt(late)} votos depois das ${cut.label} terem sido de ${esc(winner)}; o vencedor não troca.</div>`
      : late === 0
        ? `<div class="verdict ok"><b>Nenhum voto depois das ${cut.label}</b> neste recorte: uma parada nesse horário não mudaria nada.</div>`
        : `<div class="verdict ok"><b>O vencedor não muda em nenhum cenário.</b> Mesmo se todos os ${fmtInt(late)} votos depois das ${cut.label} tivessem sido de um único candidato, ${esc(winner)} continuaria à frente.</div>`;
  const semAfter = a.late ? a.semBio / a.late : null, semBefore = a.h16 ? a.h16SemBio / a.h16 : null;
  return `
  <div class="card ext-card"><h3>Se a votação parasse às ${cut.label} <span class="tag">${esc(title)}</span></h3>
    ${cutButtons(cut)}
    <div class="stats" style="margin-top:12px">
      <div><div class="stat-label">Votos depois das ${cut.label}</div><div class="stat-value">${fmtInt(late)}</div><div class="stat-sub">${pct(a.comp ? late / a.comp : null, 3)} dos votos</div></div>
      <div><div class="stat-label">Urnas que ficaram abertas até 18:55+</div><div class="stat-value">${fmtInt(a.D)}</div><div class="stat-sub">${fmtInt(a.C)} entre 17:10 e 18:55</div></div>
    </div>
    ${verdict}
    <table class="grid ext-bounds"><thead><tr><th></th><th>Oficial</th><th>Parada às ${cut.label}</th></tr></thead><tbody>
      <tr><td>${esc(cand[0].name)}</td><td>${fmtInt(a.lula)}</td><td>${fmtInt(a.lula - a.a)} –<br>${fmtInt(a.lula)}</td></tr>
      <tr><td>${esc(cand[1].name)}</td><td>${fmtInt(a.flavio)}</td><td>${fmtInt(a.flavio - a.b)} –<br>${fmtInt(a.flavio)}</td></tr>
      <tr><td>Diferença (${esc(cand[0].short)} − ${esc(cand[1].short)})</td><td>${signed(a.margin)}</td><td>${signed(a.marginMin)} a<br>${signed(a.marginMax)}</td></tr>
      <tr><td>${esc(cand[0].short)} % dos válidos</td><td>${pct(a.share, 2)}</td><td>${pct(a.shareMin, 2)} a ${pct(a.shareMax, 2)}</td></tr>
    </tbody></table>
    <p class="note">A faixa é <b>exata e não depende de hipótese</b>: o limite inferior supõe que todos os votos depois do corte foram de ${esc(cand[0].short)}, o superior que foram de ${esc(cand[1].short)} (nunca mais votos do que o candidato teve na urna). Votos sem horário no log${a.unknown ? ` (${fmtInt(a.unknown)} neste recorte)` : ''} entram como se pudessem ser depois do corte.${scopeLevel === 'country' ? ' O exterior entra com seus votos inteiros: lá não houve prorrogação (todas as urnas encerraram até 18:15, hora local).' : ''}</p>
  </div>
  <div class="card"><h3>Como votaram os eleitores depois das ${cut.label}</h3>
    <div class="compare">
      <div><div class="stat-label">Sem biometria, depois das ${cut.label}</div><div class="stat-value">${pct(semAfter, 1)}</div><div class="stat-sub">${fmtInt(a.semBio)} de ${fmtInt(a.late)} votos</div></div>
      <div><div class="stat-label">Sem biometria, 16:00–17:00 (referência)</div><div class="stat-value">${pct(semBefore, 1)}</div><div class="stat-sub">${fmtInt(a.h16SemBio)} de ${fmtInt(a.h16)} votos</div></div>
    </div>
    <p class="note">Sem biometria = falha na leitura (mesário liberou) + urna não pediu a digital. A referência é a última hora regular nos mesmos municípios. <b>Em quem</b> esses eleitores votaram não é registrado em lugar nenhum: o log guarda o horário, o RDV guarda os votos embaralhados.</p>
  </div>`;
}

export function nationalCards(cand) {
  const E = EXT, g = E.groups, r1700 = E.lean_if_like_their_urna.c1700, reg = E.place_regression.c1700, sib = E.sibling_D_vs_ontime;
  const row = x => `<tr><td><b>${x.group}</b> · ${esc(x.label)}</td><td>${fmtInt(x.urnas)}</td><td>${fmtInt(x.after_c1700)}</td><td>${fmtInt(x.after_c1710)}</td><td>${pct(x.lula_share, 1)}</td></tr>`;
  const regRows = E.regions.map(x => `<tr><td>${esc(x.region)}</td><td>${fmtInt(x.group_D)}</td><td>${fmtInt(x.after_c1700)}</td><td>${fmtInt(x.after_c1710)}</td><td>${pct(x.lula_share, 1)}</td></tr>`).join('');
  const st = E.states.slice(0, 10).map(x => `<tr><td>${esc(x.uf)}</td><td>${fmtInt(x.group_D)}</td><td>${pct(x.share_D, 1)}</td><td>${pct(x.lula_share, 1)}</td><td>${x.lula_share_D == null ? '—' : pct(x.lula_share_D, 1)}</td></tr>`).join('');
  const ci = v => `${v[0] >= 0 ? '+' : ''}${(v[0]).toFixed(2).replace('.', ',')} a ${v[1] >= 0 ? '+' : ''}${(v[1]).toFixed(2).replace('.', ',')}`;
  return `
  <div class="card"><h3>Onde ficaram as urnas abertas</h3>
    <table class="grid"><thead><tr><th>Grupo (horário de encerramento)</th><th>Urnas</th><th>Votos após 17:00</th><th>Após 17:10</th><th>${esc(cand[0].short)} % (urnas do grupo)</th></tr></thead><tbody>${g.map(row).join('')}</tbody></table>
    <h3 style="margin-top:14px">Por região</h3>
    <table class="grid"><thead><tr><th>Região</th><th>Urnas grupo D</th><th>Votos após 17:00</th><th>Após 17:10</th><th>${esc(cand[0].short)} % (região)</th></tr></thead><tbody>${regRows}</tbody></table>
    <h3 style="margin-top:14px">Estados com mais urnas no grupo D</h3>
    <table class="grid"><thead><tr><th>UF</th><th>Urnas D</th><th>% das urnas</th><th>${esc(cand[0].short)} % (estado)</th><th>${esc(cand[0].short)} % (urnas D)</th></tr></thead><tbody>${st}</tbody></table>
  </div>
  <div class="card"><h3>Estimativas <span class="tag">dependem de hipóteses — leia a nota</span></h3>
    <ul class="list est">
      <li><span class="li-main">Se os eleitores depois das 17:00 tivessem votado como o restante da própria urna</span><span class="li-val">${pct(r1700.lula_share, 1)} ${esc(cand[0].short)}</span><span class="li-sub">mostra a inclinação dos lugares onde houve voto tardio, não a escolha desses eleitores</span></li>
      <li><span class="li-main">Mesmo local de votação: urnas que ficaram até 18:55+ vs urnas que fecharam no horário</span><span class="li-val">${sib ? (sib.mean_diff_pp >= 0 ? '+' : '') + sib.mean_diff_pp.toFixed(2).replace('.', ',') + ' p.p.' : '—'}</span><span class="li-sub">${sib ? `${fmtInt(sib.places)} locais; IC 95%: ${ci(sib.ci_pp)} p.p. na fatia de ${esc(cand[0].short)}` : ''}</span></li>
      <li><span class="li-main">Regressão dentro do local de votação: fatia de ${esc(cand[0].short)} vs fração de votos após 17:00</span><span class="li-val">${reg ? (reg.beta >= 0 ? '+' : '') + (reg.beta * 100).toFixed(1).replace('.', ',') + ' p.p.' : '—'}</span><span class="li-sub">${reg ? `IC 95%: ${ci([reg.ci[0] * 100, reg.ci[1] * 100])} p.p. (diferença entre eleitores tardios e os demais do local)` : ''}</span></li>
    </ul>
    <p class="note">Estas linhas não são contagens: são comparações estatísticas, porque o voto de cada eleitor tardio não é registrado. Um intervalo largo significa que os dados não permitem dizer se os eleitores tardios votaram diferente dos demais.</p>
  </div>
  <div class="card"><h3>Conferências de qualidade dos dados</h3>
    <ul class="note" style="padding-left:18px;margin:0">
      <li>Urnas com voto registrado mais de 1 min depois do próprio encerramento: <b>${fmtInt(E.data_quality.votes_after_own_close)}</b></li>
      <li>Urnas com primeiro voto antes das 08:00 (horário de Brasília): <b>${fmtInt(E.data_quality.first_vote_before_0800)}</b></li>
      <li>Urnas sem log no pacote do TSE (votos tratados como "podem ser depois do corte"): <b>${fmtInt(E.data_quality.no_log_urnas)}</b></li>
    </ul>
    <p class="note"><a href="prorrogacao.html">Relatório completo da prorrogação ▸</a></p>
  </div>`;
}

export function urnaRows(uf, ibge, cut) {
  const U = EXT.urnas_late, out = [];
  for (let i = 0; i < U.uf.length; i++) {
    if (U.uf[i] !== uf || U.ibge[i] !== ibge) continue;
    out.push({ zs: `${U.zona[i]}/${U.secao[i]}`, loc: U.local[i], close: U.close[i], comp: U.comp[i], late: U[`${cut}_all`] ? U[`${cut}_all`][i] : null,
      a1700: U.c1700_all[i], a1710: U.c1710_all[i], a1800: U.c1800_all[i], lula: U.lula[i] + U.flavio[i] ? U.lula[i] / (U.lula[i] + U.flavio[i]) : null, group: U.group[i] });
  }
  return out.sort((p, q) => q.a1700 - p.a1700);
}
