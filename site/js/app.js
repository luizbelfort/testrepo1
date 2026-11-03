import { getJSON, StateData, sumOver } from './data.js';
import { Timeline } from './timeline.js';
import { areaChart } from './charts.js';
import { COLORS, seq, diverging, DIVERGING_SPAN, METRIC_DOMAINS, fmtInt, pct, hhmm, hhmmss } from './scales.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const S = {
  t: 0, mode: 'auto', metric: 'turnout', manualOnly: false, fastOverlay: false,
  th: null, sel: { level: 'country' }, selUrna: null, speed: 5, playing: false,
};
let M, map, timeline, statesGeo, stateFeat = new Map();
const loaded = new Map();       // uf -> StateData
const munGeo = new Map();       // uf -> geojson
let snaps = new Map();          // uf -> snapshot at S.t
let hovered = null;

// ---------------------------------------------------------------- boot
init().catch(err => {
  console.error(err);
  $('#p-body').innerHTML = `<div class="card"><div class="empty">Falha ao carregar os dados: ${esc(err.message)}</div></div>`;
});

async function init() {
  M = await getJSON('data/manifest.json');
  $('#election-name').textContent = M.election.label;
  S.th = { ...M.fast_bins.defaults };
  S.t = M.time.vote_t0;
  statesGeo = await getJSON(M.geo.states);
  for (const f of statesGeo.features) stateFeat.set(f.properties.uf, f);
  await initMap();
  for (const st of M.states.filter(s => s.loaded)) await loadState(st.uf);
  timeline = new Timeline({
    track: $('#tl-track'), canvas: $('#tl-canvas'), markersEl: $('#tl-markers'), handle: $('#tl-handle'),
    manifest: M, onChange: t => { S.t = t; scheduleRender(); },
  });
  window.__setT = t => timeline.set(t);   // used by automated UI checks
  bindUI();
  buildAbout();
  buildRegions();
  timeline.set(S.t);
  render();
}

async function loadState(uf) {
  const st = M.states.find(s => s.uf === uf);
  const [raw, geo] = await Promise.all([getJSON(st.file), getJSON(st.geo)]);
  const sd = new StateData(M, raw);
  loaded.set(uf, sd); munGeo.set(uf, geo);
  map.addSource(`mun-${uf}`, { type: 'geojson', data: geo, promoteId: 'id' });
  map.addLayer({ id: `mun-${uf}-fill`, type: 'fill', source: `mun-${uf}`, paint: {
    'fill-color': ['coalesce', ['feature-state', 'color'], COLORS.noData], 'fill-opacity': 1 } }, 'states-line');
  map.addLayer({ id: `mun-${uf}-line`, type: 'line', source: `mun-${uf}`, paint: {
    'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], '#f0efec', ['boolean', ['feature-state', 'hover'], false], '#c3c2b7', '#0a0a0b'],
    'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.2, ['boolean', ['feature-state', 'hover'], false], 1.6, 0.35] } }, 'states-line');
  const pts = { type: 'FeatureCollection', features: raw.munis.ibge.map((id, i) => ({
    type: 'Feature', id: i, properties: { id }, geometry: { type: 'Point', coordinates: [raw.munis.lon[i], raw.munis.lat[i]] } })) };
  map.addSource(`pts-${uf}`, { type: 'geojson', data: pts, promoteId: 'id' });
  map.addLayer({ id: `pts-${uf}`, type: 'circle', source: `pts-${uf}`, layout: { visibility: 'none' }, paint: {
    'circle-radius': ['coalesce', ['feature-state', 'r'], 0], 'circle-color': COLORS.amber, 'circle-opacity': 0.75,
    'circle-stroke-color': '#0a0a0b', 'circle-stroke-width': 1 } });
  for (const ev of ['mousemove', 'click']) map.on(ev, `mun-${uf}-fill`, e => onMunEvent(ev, uf, e));
  map.on('mouseleave', `mun-${uf}-fill`, clearHover);
}

// ---------------------------------------------------------------- map
async function initMap() {
  map = new maplibregl.Map({
    container: 'map', attributionControl: false,
    style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0a0a0b' } }] },
    bounds: [[-74.5, -34.5], [-34.5, 5.8]], fitBoundsOptions: { padding: 30 }, dragRotate: false, pitchWithRotate: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'Dados: TSE · Malhas: IBGE (via geodata-br)' }));
  await new Promise(r => map.on('load', r));
  map.addSource('states', { type: 'geojson', data: statesGeo, promoteId: 'uf' });
  map.addLayer({ id: 'states-fill', type: 'fill', source: 'states', paint: {
    'fill-color': ['coalesce', ['feature-state', 'color'], COLORS.noData] } });
  map.addLayer({ id: 'states-line', type: 'line', source: 'states', paint: {
    'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], '#f0efec', '#4a4a50'],
    'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2, 0.9] } });
  map.on('click', 'states-fill', e => {
    const uf = e.features[0].properties.uf;
    if (!loaded.has(uf)) select({ level: 'state', uf });
  });
  map.on('mousemove', 'states-fill', e => {
    const uf = e.features[0].properties.uf;
    if (loaded.has(uf)) return;
    map.getCanvas().style.cursor = 'pointer';
    showTip(e.point, `<div class="tt-title">${esc(stateName(uf))}</div><div class="tt-row">Dados ainda não carregados</div>`);
  });
  map.on('mouseleave', 'states-fill', clearHover);
}

function onMunEvent(ev, uf, e) {
  const f = e.features[0]; const id = f.properties.id;
  if (ev === 'click') {
    if (S.sel.level === 'country' || S.sel.level === 'region') select({ level: 'state', uf });
    else select({ level: 'muni', uf, ibge: id });
    return;
  }
  map.getCanvas().style.cursor = 'pointer';
  if (hovered?.id !== id) {
    clearHover(true);
    hovered = { uf, id };
    map.setFeatureState({ source: `mun-${uf}`, id }, { hover: true });
  }
  showTip(e.point, munTooltip(uf, id));
}
function clearHover(keepTip) {
  if (hovered) map.setFeatureState({ source: `mun-${hovered.uf}`, id: hovered.id }, { hover: false });
  hovered = null; map.getCanvas().style.cursor = '';
  if (keepTip !== true) $('#tooltip').hidden = true;
}
function showTip(pt, html) {
  const tip = $('#tooltip'); tip.innerHTML = html; tip.hidden = false;
  const W = $('#map').clientWidth;
  tip.style.left = `${Math.min(W - 230, pt.x + 14)}px`; tip.style.top = `${pt.y + 14}px`;
}

// ---------------------------------------------------------------- selection
function stateName(uf) { return M.states.find(s => s.uf === uf)?.name ?? uf; }
function regionOf(uf) { return M.states.find(s => s.uf === uf)?.region; }

function scopeStates(sel = S.sel) {
  if (sel.level === 'country') return M.states.map(s => s.uf);
  if (sel.level === 'region') return M.regions.find(r => r.key === sel.key).ufs;
  return [sel.uf];
}
function scopeMunis(uf, sel = S.sel) {
  const sd = loaded.get(uf); if (!sd) return [];
  if (sel.level === 'muni') return [sd.munIndex.get(sel.ibge)];
  return [...Array(sd.nMun).keys()];
}

function bboxOf(features) {
  let b = [180, 90, -180, -90];
  const walk = c => { if (typeof c[0] === 'number') { b = [Math.min(b[0], c[0]), Math.min(b[1], c[1]), Math.max(b[2], c[0]), Math.max(b[3], c[1])]; } else c.forEach(walk); };
  features.forEach(f => walk(f.geometry.coordinates));
  return [[b[0], b[1]], [b[2], b[3]]];
}

function select(sel, { fly = true } = {}) {
  const prev = S.sel;
  if (prev.level === 'muni') map.setFeatureState({ source: `mun-${prev.uf}`, id: prev.ibge }, { sel: false });
  if (prev.uf && stateFeat.has(prev.uf)) map.setFeatureState({ source: 'states', id: prev.uf }, { sel: false });
  const changed = JSON.stringify(prev) !== JSON.stringify(sel);
  S.sel = sel; if (sel.level !== 'muni') S.selUrna = null;
  if (changed) document.querySelector('.panel-scroll').scrollTop = 0;
  if (sel.level === 'muni') map.setFeatureState({ source: `mun-${sel.uf}`, id: sel.ibge }, { sel: true });
  if (sel.level === 'state') map.setFeatureState({ source: 'states', id: sel.uf }, { sel: true });
  if (fly) {
    let feats;
    if (sel.level === 'country') feats = statesGeo.features;
    else if (sel.level === 'region') feats = statesGeo.features.filter(f => M.regions.find(r => r.key === sel.key).ufs.includes(f.properties.uf));
    else if (sel.level === 'state') feats = [stateFeat.get(sel.uf)];
    else feats = munGeo.get(sel.uf).features.filter(f => f.properties.id === sel.ibge);
    map.fitBounds(bboxOf(feats), { padding: { top: 90, bottom: 70, left: 40, right: 40 }, duration: 700, maxZoom: sel.level === 'muni' ? 8.5 : 9 });
  }
  document.querySelectorAll('#regions button').forEach(b => b.classList.toggle('on', sel.level === 'region' && b.dataset.key === sel.key));
  render();
}

function crumbs() {
  const c = [{ label: 'Brasil', sel: { level: 'country' } }];
  const s = S.sel;
  const reg = s.level === 'region' ? s.key : s.uf ? regionOf(s.uf) : null;
  if (reg) c.push({ label: M.regions.find(r => r.key === reg).name, sel: { level: 'region', key: reg } });
  if (s.uf) c.push({ label: stateName(s.uf), sel: { level: 'state', uf: s.uf } });
  if (s.level === 'muni') c.push({ label: munName(s.uf, s.ibge), sel: s });
  const el = $('#crumbs'); el.innerHTML = '';
  c.forEach((x, i) => {
    if (i) { const sp = document.createElement('span'); sp.className = 'sep'; sp.textContent = '›'; el.appendChild(sp); }
    const b = document.createElement('button'); b.type = 'button'; b.textContent = x.label;
    b.addEventListener('click', () => select(x.sel)); el.appendChild(b);
  });
}
function munName(uf, ibge) { const sd = loaded.get(uf); return sd ? sd.raw.munis.name[sd.munIndex.get(ibge)] : ibge; }

function buildRegions() {
  const el = $('#regions');
  for (const r of M.regions) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = r.name; b.dataset.key = r.key;
    b.addEventListener('click', () => select({ level: 'region', key: r.key })); el.appendChild(b);
  }
}

// ---------------------------------------------------------------- render loop
let raf = 0, lastPanel = 0, panelTimer = 0;
function scheduleRender() {
  if (raf) return;
  raf = requestAnimationFrame(() => { raf = 0; render(false); });
}
function effectiveMode() {
  if (S.mode !== 'auto') return S.mode;
  const end = M.markers.find(m => m.key === 'ext_end')?.t ?? M.markers.find(m => m.key === 'close_regular').t;
  return S.t < end ? 'vote' : 'count';
}
function phaseLabel() {
  const mk = Object.fromEntries(M.markers.map(m => [m.key, m.t]));
  if (S.t < mk.open) return 'antes da abertura';
  if (S.t < mk.close_regular) return 'votação';
  if (S.t < mk.ext_end) return S.t < mk.ext_start ? 'encerramento (filas)' : 'urnas ainda abertas';
  if (S.t < mk.last_bu) return 'apuração';
  return 'apuração concluída';
}

function render(full = true) {
  for (const [uf, sd] of loaded) snaps.set(uf, sd.snapshot(S.t, S.th));
  $('#tl-time').textContent = hhmm(S.t);
  $('#tl-phase').textContent = phaseLabel();
  paintMap();
  renderLegend();
  crumbs();
  const now = performance.now();
  clearTimeout(panelTimer);
  if (full || now - lastPanel > 150) { lastPanel = now; renderPanel(); }
  else panelTimer = setTimeout(() => { lastPanel = performance.now(); renderPanel(); }, 160);
  if (full) updateTimelineContext();
}

function munValue(uf, i) {
  const s = snaps.get(uf), sd = loaded.get(uf), aptos = sd.raw.munis.aptos[i];
  const mode = effectiveMode();
  if (mode === 'count') {
    if (S.manualOnly) return s.countedComp[i] ? { v: s.countedManual[i] / s.countedComp[i], kind: 'seq', dom: 'manualCount' } : { v: null, kind: 'uncounted' };
    const valid = s.lula[i] + s.flavio[i];
    return valid ? { v: s.lula[i] / valid, kind: 'div' } : { v: null, kind: 'uncounted' };
  }
  if (S.metric === 'turnout') return S.manualOnly ? { v: s.manual[i] / aptos, kind: 'seq', dom: 'turnoutManual' } : { v: s.votes[i] / aptos, kind: 'seq', dom: 'turnout' };
  if (S.metric === 'manual') return { v: s.votes[i] ? s.manual[i] / s.votes[i] : null, kind: 'seq', dom: 'manual' };
  return { v: s.manual[i] ? s.fast[i] / s.manual[i] : null, kind: 'seq', dom: 'fast' };
}
function colorFor(val) {
  if (val.kind === 'uncounted') return COLORS.uncounted;
  if (val.v == null) return COLORS.uncounted;
  if (val.kind === 'div') return diverging(val.v);
  return seq(val.v / METRIC_DOMAINS[val.dom].max);
}

function paintMap() {
  let fastMax = 1;
  for (const [uf, s] of snaps) for (const v of s.fast) fastMax = Math.max(fastMax, v);
  for (const [uf, sd] of loaded) {
    const s = snaps.get(uf);
    for (let i = 0; i < sd.nMun; i++) {
      const id = sd.raw.munis.ibge[i];
      map.setFeatureState({ source: `mun-${uf}`, id }, { color: colorFor(munValue(uf, i)) });
      map.setFeatureState({ source: `pts-${uf}`, id }, { r: s.fast[i] ? 3 + 16 * Math.sqrt(s.fast[i] / fastMax) : 0 });
    }
    map.setLayoutProperty(`pts-${uf}`, 'visibility', S.fastOverlay && effectiveMode() === 'vote' ? 'visible' : 'none');
    map.setFeatureState({ source: 'states', id: uf }, { color: '#0a0a0b' });
  }
  const note = $('#map-note');
  if (effectiveMode() === 'count' && S.manualOnly) {
    note.hidden = false;
    note.innerHTML = '<b>O voto não fica vinculado ao modo de habilitação.</b> O log registra <i>que</i> o eleitor votou, mas não em quem; o RDV embaralha os votos. Por isso, na apuração este filtro mostra a <b>proporção de votos sem biometria</b> nas urnas já apuradas, sem cores de candidato.';
  } else if (effectiveMode() === 'count' && S.fastOverlay) {
    note.hidden = false; note.textContent = 'Os votos rápidos são mostrados no modo Votação (a apuração não informa em quem cada voto rápido foi dado).';
  } else note.hidden = true;
}

function renderLegend() {
  const el = $('#legend'), mode = effectiveMode();
  const sample = (f, n = 12) => Array.from({ length: n }, (_, i) => f(i / (n - 1)));
  if (mode === 'count' && !S.manualOnly) {
    const left = sample(x => diverging(0.5 - DIVERGING_SPAN + x * DIVERGING_SPAN * 2));
    const c = M.election.candidates;
    el.innerHTML = `<div class="legend-title">Apuração até ${hhmm(S.t)} · votos válidos</div>
      <div class="legend-bar" style="background:linear-gradient(90deg,${left.join(',')})"></div>
      <div class="legend-ticks"><span>${esc(c[1].short || c[1].name)} ≥${pct(0.5 + DIVERGING_SPAN, 0)}</span><span>empate</span><span>${esc(c[0].short || c[0].name)} ≥${pct(0.5 + DIVERGING_SPAN, 0)}</span></div>
      <div class="legend-row"><span class="legend-swatch" style="background:${COLORS.uncounted}"></span>Nenhuma urna apurada ainda</div>
      <div class="legend-row"><span class="legend-swatch" style="background:${COLORS.noData}"></span>Dados não carregados</div>`;
    return;
  }
  const dom = mode === 'count' ? 'manualCount' : S.metric === 'turnout' ? (S.manualOnly ? 'turnoutManual' : 'turnout') : S.metric;
  const D = METRIC_DOMAINS[dom];
  el.innerHTML = `<div class="legend-title">${esc(D.title)}</div>
    <div class="legend-bar" style="background:linear-gradient(90deg,${sample(seq).join(',')})"></div>
    <div class="legend-ticks"><span>0%</span><span>${D.fmt(D.max / 2)}</span><span>≥${D.fmt(D.max)}</span></div>
    ${S.fastOverlay && mode === 'vote' ? `<div class="legend-row"><span class="legend-swatch" style="background:${COLORS.amber};border-radius:50%"></span>Círculo: quantidade de votos rápidos</div>` : ''}
    <div class="legend-row"><span class="legend-swatch" style="background:${COLORS.noData}"></span>Dados não carregados</div>`;
}

function updateTimelineContext() {
  // silhouette = votes per bucket for the current scope; bars = BUs received per 5 min
  const T = M.time, votes = new Float64Array(T.vote_n);
  let recvT0 = Infinity, recvT1 = -Infinity;
  const recvTimes = [];
  for (const uf of scopeStates()) {
    const sd = loaded.get(uf); if (!sd) continue;
    const idx = scopeMunis(uf);
    const v = sd.seriesFor(idx, S.manualOnly ? 'manual' : 'votes');
    for (let j = 0; j < v.length; j++) votes[j] += v[j];
    const set = new Set(idx);
    for (let k = 0; k < sd.nUrna; k++) if (set.has(sd.u.m[k]) && sd.u.recv[k] >= 0) { recvTimes.push(sd.u.recv[k]); }
  }
  for (const t of recvTimes) { recvT0 = Math.min(recvT0, t); recvT1 = Math.max(recvT1, t); }
  let recv = null;
  if (recvTimes.length) {
    const step = 300, t0 = Math.floor(recvT0 / step) * step, n = Math.ceil((recvT1 - t0 + 1) / step);
    const counts = new Float64Array(n); for (const t of recvTimes) counts[Math.floor((t - t0) / step)]++;
    recv = { t0, step, counts };
  }
  timeline.setContext({ votes, recv });
}

// ---------------------------------------------------------------- panel
function aggregate() {
  const tot = { aptos: 0, urnas: 0, statesLoaded: 0, statesTotal: 0 };
  let acc = null;
  for (const uf of scopeStates()) {
    tot.statesTotal++;
    const sd = loaded.get(uf); if (!sd) continue;
    tot.statesLoaded++;
    const idx = scopeMunis(uf);
    const s = sumOver(snaps.get(uf), idx);
    for (const i of idx) { tot.aptos += sd.raw.munis.aptos[i]; tot.urnas += sd.raw.munis.urnas[i]; }
    if (!acc) acc = s; else for (const k in s) acc[k] += s[k];
  }
  return { ...tot, ...(acc || {}) };
}

function renderPanel() {
  const sel = S.sel, a = aggregate(), mode = effectiveMode();
  const title = sel.level === 'country' ? 'Brasil' : sel.level === 'region' ? M.regions.find(r => r.key === sel.key).name : sel.level === 'state' ? stateName(sel.uf) : munName(sel.uf, sel.ibge);
  $('#p-kicker').textContent = { country: 'País', region: 'Região', state: 'Estado', muni: `Município · ${sel.uf}` }[sel.level];
  $('#p-title').textContent = title;
  $('#p-sub').textContent = a.statesLoaded
    ? `${fmtInt(a.urnas)} urnas · ${fmtInt(a.aptos)} eleitores aptos${a.statesTotal > 1 ? ` · ${a.statesLoaded} de ${a.statesTotal} estados com dados carregados` : ''}`
    : 'Dados deste estado ainda não foram processados.';
  const body = $('#p-body');
  if (!a.statesLoaded) { body.innerHTML = `<div class="card"><div class="empty">Os arquivos de urna deste estado ainda não foram baixados e processados. Estados com dados: ${M.states.filter(s => s.loaded).map(s => s.name).join(', ')}.</div></div>`; return; }
  const parts = [];
  parts.push(statusCard(a));
  parts.push(mode === 'count' ? countCard(a) : voteCard(a));
  parts.push(`<div class="card"><h3>${S.manualOnly ? 'Votos sem biometria' : 'Votos'} a cada ${M.time.vote_step / 60} min</h3><div class="chart" id="ch-votes"></div>
    <h3 style="margin-top:14px">Votos sem biometria a cada ${M.time.vote_step / 60} min</h3><div class="chart" id="ch-manual"></div></div>`);
  parts.push(fastCard(a));
  parts.push(`<div class="card"><h3>Padrões para conferir <span class="tag">ordenados pelos dados, sem juízo</span></h3><div id="patterns"></div></div>`);
  if (sel.level === 'muni') parts.push(`<div class="card"><h3>Urnas do município</h3><div id="urnas"><div class="empty">Carregando urnas…</div></div></div>`);
  else if (sel.level === 'state') parts.push(`<div class="card"><h3>Municípios (tabela)</h3><div id="munis"></div></div>`);
  body.innerHTML = parts.join('');
  drawCharts();
  bindFast();
  renderPatterns();
  if (sel.level === 'muni') renderUrnas();
  if (sel.level === 'state') renderMunTable();
}

function statusCard(a) {
  return `<div class="card"><div class="stats">
    <div><div class="stat-label">Urnas abertas</div><div class="stat-value">${fmtInt(a.open)}</div><div class="stat-sub">de ${fmtInt(a.urnas)}</div></div>
    <div><div class="stat-label">Urnas encerradas</div><div class="stat-value">${fmtInt(a.closed)}</div><div class="stat-sub">${pct(a.closed / a.urnas)}</div></div>
    <div><div class="stat-label">BUs recebidos pelo TSE</div><div class="stat-value">${fmtInt(a.counted)}</div><div class="stat-sub">${pct(a.counted / a.urnas)}</div></div>
    <div><div class="stat-label">Horário</div><div class="stat-value">${hhmm(S.t)}</div><div class="stat-sub">${phaseLabel()}</div></div>
  </div></div>`;
}

function voteCard(a) {
  return `<div class="card"><h3>Votação até ${hhmm(S.t)}</h3><div class="stats">
    <div><div class="stat-label">Votos registrados</div><div class="stat-value">${fmtInt(a.votes)}</div><div class="stat-sub">${pct(a.votes / a.aptos)} dos aptos</div></div>
    <div><div class="stat-label">Sem biometria</div><div class="stat-value">${fmtInt(a.manual)}</div><div class="stat-sub">${pct(a.manual / a.votes)} dos votos</div></div>
    <div><div class="stat-label">Sem digital cadastrada</div><div class="stat-value">${fmtInt(a.nofp)}</div><div class="stat-sub">${pct(a.nofp / a.votes)} dos votos</div></div>
    <div><div class="stat-label">Com biometria</div><div class="stat-value">${fmtInt(a.votes - a.manual - a.nofp)}</div><div class="stat-sub">${pct((a.votes - a.manual - a.nofp) / a.votes)} dos votos</div></div>
  </div>
  <p class="note"><b>Sem biometria</b>: o eleitor tinha digital cadastrada, a leitura falhou, e um mesário o habilitou após conferir dados pessoais (é o número que o BU chama de "não habilitados por biometria"). <b>Sem digital cadastrada</b>: a urna não pediu a digital.</p></div>`;
}

function countCard(a) {
  const c = M.election.candidates, valid = a.lula + a.flavio;
  const row = (cand, v, col) => `<div class="cand"><div class="cand-name"><span class="cand-swatch" style="background:${col}"></span>${esc(cand.name)} <span class="stat-sub">${cand.number} · ${esc(cand.party)}</span></div>
    <div class="cand-pct">${pct(valid ? v / valid : null)}</div><div class="cand-votes">${fmtInt(v)} votos</div>
    <div class="cand-bar"><span style="width:${valid ? (100 * v) / valid : 0}%;background:${col}"></span></div></div>`;
  return `<div class="card"><h3>Apuração até ${hhmm(S.t)} <span class="tag">${fmtInt(a.counted)} de ${fmtInt(a.urnas)} urnas (${pct(a.counted / a.urnas)})</span></h3>
    ${row(c[0], a.lula, COLORS.lula)}${row(c[1], a.flavio, COLORS.flavio)}
    <div class="stats" style="margin-top:12px">
      <div><div class="stat-label">Brancos</div><div class="stat-value">${fmtInt(a.branco)}</div></div>
      <div><div class="stat-label">Nulos</div><div class="stat-value">${fmtInt(a.nulo)}</div></div>
    </div>
    <p class="note">Cada urna entra na soma no horário em que o TSE registrou o recebimento do seu Boletim de Urna (campo <code>DT_BU_RECEBIDO</code>).</p></div>`;
}

function drawCharts() {
  const T = M.time, votes = new Float64Array(T.vote_n), manual = new Float64Array(T.vote_n);
  for (const uf of scopeStates()) {
    const sd = loaded.get(uf); if (!sd) continue;
    const idx = scopeMunis(uf);
    const v = sd.seriesFor(idx, S.manualOnly ? 'manual' : 'votes'), m = sd.seriesFor(idx, 'manual');
    for (let j = 0; j < v.length; j++) { votes[j] += v[j]; manual[j] += m[j]; }
  }
  areaChart($('#ch-votes'), { series: votes, t0: T.vote_t0, step: T.vote_step, cursor: S.t, color: '#1baf7a', label: S.manualOnly ? 'Votos sem biometria' : 'Votos' });
  areaChart($('#ch-manual'), { series: manual, t0: T.vote_t0, step: T.vote_step, cursor: S.t, color: '#9a9890', label: 'Votos sem biometria' });
}

// ---------------------------------------------------------------- fast votes
function med(k) { const v = M.fast_medians?.[k]; return v == null ? '—' : `${Math.round(v)} s`; }
function binLabel(arr, i, unit = 's') { return arr[i] == null ? 'qualquer tempo' : `≤ ${arr[i]} ${unit}`; }
function fastCard(a) {
  const B = M.fast_bins;
  const slider = (key, label, desc) => `<div class="slider-row"><label for="sl-${key}">${label}<b id="lb-${key}">${binLabel(B[key], S.th[key])}</b></label>
    <input id="sl-${key}" type="range" min="0" max="${B[key].length - 1}" step="1" value="${S.th[key]}" aria-describedby="ds-${key}">
    <div class="note" id="ds-${key}" style="margin-top:2px">${desc}</div></div>`;
  const shareManual = a.manual ? a.fastVoteManual / a.manual : null, shareBio = a.bioAll ? a.fastVoteBio / a.bioAll : null;
  return `<div class="card"><h3><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M13 2 4 14h7l-1 8 9-12h-7z" fill="${COLORS.amber}"/></svg>Votos rápidos <span class="tag">critério ajustável</span></h3>
    <div class="stats">
      <div><div class="stat-label">Atendem aos 3 critérios</div><div class="stat-value" style="color:${COLORS.amber}">${fmtInt(a.fast)}</div><div class="stat-sub">${pct(a.manual ? a.fast / a.manual : null, 2)} dos votos sem biometria</div></div>
      <div><div class="stat-label">Até ${hhmm(S.t)}</div><div class="stat-value">${fmtInt(a.manual)}</div><div class="stat-sub">votos sem biometria</div></div>
    </div>
    ${slider('fp', '1. Leituras de digital até a liberação manual', `Do 1º pedido de digital até a urna pedir os dados pessoais. Mediana: ${med('fp')}.`)}
    ${slider('rel', '2. Liberação pelo mesário', `Do pedido de dados pessoais até a digital do mesário liberar o eleitor. Mediana: ${med('rel')}.`)}
    ${slider('vote', '3. Voto concluído', `Da habilitação do eleitor até o voto ser computado. Mediana: ${med('vote_manual')} (sem biometria) e ${med('vote_bio')} (com biometria).`)}
    <div class="compare">
      <div><div class="stat-label">Sem biometria: voto ${binLabel(B.vote, S.th.vote)}</div><div class="stat-value">${pct(shareManual, 2)}</div><div class="stat-sub">${fmtInt(a.fastVoteManual)} votos</div></div>
      <div><div class="stat-label">Com biometria: voto ${binLabel(B.vote, S.th.vote)}</div><div class="stat-value">${pct(shareBio, 2)}</div><div class="stat-sub">${fmtInt(a.fastVoteBio)} votos · referência</div></div>
    </div>
    <p class="note">Compare as duas caixas: votos rápidos também acontecem entre eleitores identificados pela digital. Um voto rápido <b>não</b> é, por si só, evidência de irregularidade — é um padrão para conferir.</p></div>`;
}
function bindFast() {
  for (const key of ['fp', 'rel', 'vote']) {
    const el = $(`#sl-${key}`); if (!el) continue;
    el.addEventListener('input', () => { $(`#lb-${key}`).textContent = binLabel(M.fast_bins[key], +el.value); });
    el.addEventListener('change', () => { S.th[key] = +el.value; render(); });
  }
}

// ---------------------------------------------------------------- patterns (ranked lists)
function renderPatterns() {
  const el = $('#patterns'); if (!el) return;
  const sel = S.sel, t = S.t, out = [];
  const listHTML = (title, items, empty) => `<h3 style="margin-top:6px">${title}</h3>${items.length ? `<ul class="list">${items.join('')}</ul>` : `<div class="empty">${empty}</div>`}`;
  const urnaItems = [], lateItems = [], munItems = [];
  for (const uf of scopeStates()) {
    const sd = loaded.get(uf); if (!sd) continue;
    const u = sd.u, set = new Set(scopeMunis(uf)), snap = snaps.get(uf);
    for (let k = 0; k < sd.nUrna; k++) {
      if (!set.has(u.m[k]) || u.close[k] < 0 || u.close[k] > t) continue;
      urnaItems.push({ uf, k, v: u.comp[k] ? u.manual[k] / u.comp[k] : 0 });
      lateItems.push({ uf, k, v: u.close[k] });
    }
    if (sel.level !== 'muni') for (const i of set) if (snap.manual[i] >= 30) munItems.push({ uf, i, v: snap.fast[i] / snap.manual[i], n: snap.fast[i], m: snap.manual[i] });
  }
  const urnaLi = (x, val) => { const sd = loaded.get(x.uf), u = sd.u, k = x.k;
    return `<li data-uf="${x.uf}" data-k="${k}"><span class="li-main">${esc(sd.raw.munis.name[u.m[k]])} · zona ${u.z[k]}, seção ${u.s[k]}</span><span class="li-val">${val}</span><span class="li-sub">${esc(sd.raw.models[u.model[k]] || '')} · encerrou ${hhmmss(u.close[k])}</span></li>`; };
  urnaItems.sort((p, q) => q.v - p.v);
  out.push(listHTML('Urnas com maior proporção de votos sem biometria', urnaItems.slice(0, 6).map(x => urnaLi(x, pct(x.v))), 'Nenhuma urna encerrada até este horário.'));
  lateItems.sort((p, q) => q.v - p.v);
  out.push(listHTML('Urnas encerradas mais tarde', lateItems.slice(0, 6).map(x => urnaLi(x, hhmm(x.v))), 'Nenhuma urna encerrada até este horário.'));
  if (sel.level !== 'muni') {
    munItems.sort((p, q) => q.v - p.v);
    out.push(listHTML('Municípios com maior proporção de votos rápidos', munItems.slice(0, 6).map(x => {
      const sd = loaded.get(x.uf);
      return `<li data-uf="${x.uf}" data-ibge="${sd.raw.munis.ibge[x.i]}"><span class="li-main">${esc(sd.raw.munis.name[x.i])}</span><span class="li-val"><span class="flag">${pct(x.v, 1)}</span></span><span class="li-sub">${fmtInt(x.n)} de ${fmtInt(x.m)} votos sem biometria</span></li>`;
    }), 'Sem municípios com ao menos 30 votos sem biometria até este horário.'));
  }
  el.innerHTML = out.join('') + `<p class="note">Listas apenas ordenam os números. Explicações comuns e legítimas existem (filas no fechamento, leitores biométricos com defeito, eleitores idosos ou trabalhadores manuais com digitais desgastadas).</p>`;
  el.querySelectorAll('li').forEach(li => li.addEventListener('click', () => {
    const uf = li.dataset.uf;
    if (li.dataset.ibge) return select({ level: 'muni', uf, ibge: li.dataset.ibge });
    const sd = loaded.get(uf), k = +li.dataset.k;
    S.selUrna = k; select({ level: 'muni', uf, ibge: sd.raw.munis.ibge[sd.u.m[k]] });
  }));
}

// ---------------------------------------------------------------- tables
let urnaSort = { key: 'fast', asc: false }, munSort = { key: 'votes', asc: false };
function sortableTable(cols, rows, sortState, onSort, rowAttrs = () => '') {
  const r = [...rows].sort((p, q) => {
    const a = p[sortState.key], b = q[sortState.key];
    const c = (a ?? -Infinity) > (b ?? -Infinity) ? 1 : (a ?? -Infinity) < (b ?? -Infinity) ? -1 : 0;
    return sortState.asc ? c : -c;
  });
  return `<div class="table-wrap"><table class="grid"><thead><tr>${cols.map(c => `<th data-key="${c.key}" class="${sortState.key === c.key ? 'sorted' + (sortState.asc ? ' asc' : '') : ''}">${c.label}</th>`).join('')}</tr></thead>
    <tbody>${r.map(row => `<tr ${rowAttrs(row)}>${cols.map(c => `<td>${c.fmt ? c.fmt(row[c.key], row) : esc(row[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

async function renderUrnas() {
  const { uf, ibge } = S.sel, sd = loaded.get(uf), mi = sd.munIndex.get(ibge);
  const F = await sd.loadMunFast(ibge);
  if (S.sel.ibge !== ibge) return;
  const el = $('#urnas'); if (!el) return;
  const T = M.time, fb = sd.fastBucketsDone(S.t), th = S.th, u = sd.u;
  const per = new Map();
  for (const k of sd.urnasByMun[mi]) per.set(k, { votes: 0, manual: 0, fast: 0 });
  F.series.u.forEach((k, j) => { const p = per.get(k); for (let b = 0; b < fb; b++) { p.votes += F.series.votes[j][b]; p.manual += F.series.manual[j][b]; } });
  const fm = F.manual;
  for (let i = 0; i < fm.u.length; i++) if (fm.tb[i] < fb && fm.vote[i] <= th.vote && fm.fp[i] <= th.fp && fm.rel[i] <= th.rel) per.get(fm.u[i]).fast += fm.n[i];
  const rows = sd.urnasByMun[mi].map(k => {
    const p = per.get(k), recvd = u.recv[k] >= 0 && u.recv[k] <= S.t, valid = u.lula[k] + u.flavio[k];
    return { k, zs: `${u.z[k]}/${u.s[k]}`, loc: u.loc[k], aptos: u.aptos[k], votes: p.votes, manualPct: p.votes ? p.manual / p.votes : null, fast: p.fast,
      close: u.close[k] >= 0 && u.close[k] <= S.t ? u.close[k] : null, recv: recvd ? u.recv[k] : null,
      lula: recvd && valid ? u.lula[k] / valid : null, model: sd.raw.models[u.model[k]] };
  });
  const cols = [
    { key: 'zs', label: 'Zona/Seção' }, { key: 'loc', label: 'Local' }, { key: 'model', label: 'Modelo' },
    { key: 'votes', label: 'Votos', fmt: fmtInt }, { key: 'manualPct', label: 'Sem biom.', fmt: v => pct(v) },
    { key: 'fast', label: '⚡ Rápidos', fmt: v => (v ? `<span class="flag">${v}</span>` : '0') },
    { key: 'close', label: 'Encerrou', fmt: v => (v == null ? 'aberta' : hhmmss(v)) },
    { key: 'recv', label: 'BU recebido', fmt: v => (v == null ? '—' : hhmm(v)) },
    { key: 'lula', label: `${esc(M.election.candidates[0].name)} %`, fmt: v => pct(v) },
  ];
  el.innerHTML = sortableTable(cols, rows, urnaSort, null, r => `data-k="${r.k}" class="${r.k === S.selUrna ? 'sel' : ''}"`) +
    `<p class="note">Valores até ${hhmm(S.t)} (blocos de ${T.fast_step / 60} min). O resultado de cada urna só aparece depois do horário de recebimento do seu BU.</p>`;
  el.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
    urnaSort = { key: th.dataset.key, asc: urnaSort.key === th.dataset.key ? !urnaSort.asc : false }; renderUrnas();
  }));
  el.querySelectorAll('tr[data-k]').forEach(tr => tr.addEventListener('click', () => { S.selUrna = +tr.dataset.k; renderUrnas(); }));
  el.querySelector('tr.sel')?.scrollIntoView({ block: 'nearest' });
}

function renderMunTable() {
  const el = $('#munis'); if (!el) return;
  const sd = loaded.get(S.sel.uf), s = snaps.get(S.sel.uf), m = sd.raw.munis;
  const rows = m.ibge.map((id, i) => ({ id, name: m.name[i], urnas: m.urnas[i], votes: s.votes[i], turnout: s.votes[i] / m.aptos[i],
    manualPct: s.votes[i] ? s.manual[i] / s.votes[i] : null, fast: s.fast[i],
    lula: s.lula[i] + s.flavio[i] ? s.lula[i] / (s.lula[i] + s.flavio[i]) : null, counted: s.counted[i] / m.urnas[i] }));
  const cols = [
    { key: 'name', label: 'Município' }, { key: 'urnas', label: 'Urnas', fmt: fmtInt }, { key: 'votes', label: 'Votos', fmt: fmtInt },
    { key: 'turnout', label: 'Compar.', fmt: v => pct(v, 0) }, { key: 'manualPct', label: 'Sem biom.', fmt: v => pct(v) },
    { key: 'fast', label: '⚡', fmt: v => (v ? `<span class="flag">${fmtInt(v)}</span>` : '0') },
    { key: 'counted', label: 'Apurado', fmt: v => pct(v, 0) }, { key: 'lula', label: `${esc(M.election.candidates[0].name)} %`, fmt: v => pct(v) },
  ];
  el.innerHTML = sortableTable(cols, rows, munSort, null, r => `data-id="${r.id}"`);
  el.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
    munSort = { key: th.dataset.key, asc: munSort.key === th.dataset.key ? !munSort.asc : false }; renderMunTable();
  }));
  el.querySelectorAll('tr[data-id]').forEach(tr => tr.addEventListener('click', () => select({ level: 'muni', uf: S.sel.uf, ibge: tr.dataset.id })));
}

function munTooltip(uf, id) {
  const sd = loaded.get(uf), i = sd.munIndex.get(id), s = snaps.get(uf), m = sd.raw.munis;
  const row = (l, v) => `<div class="tt-row">${l}<b>${v}</b></div>`;
  const valid = s.lula[i] + s.flavio[i], c = M.election.candidates;
  return `<div class="tt-title">${esc(m.name[i])} · ${uf}</div>` +
    (effectiveMode() === 'count'
      ? row('Urnas apuradas', `${fmtInt(s.counted[i])}/${fmtInt(m.urnas[i])}`) + row(esc(c[0].name), pct(valid ? s.lula[i] / valid : null)) + row(esc(c[1].name), pct(valid ? s.flavio[i] / valid : null)) + row('Sem biometria (apuradas)', pct(s.countedComp[i] ? s.countedManual[i] / s.countedComp[i] : null))
      : row('Votos', `${fmtInt(s.votes[i])} (${pct(s.votes[i] / m.aptos[i], 0)})`) + row('Sem biometria', `${fmtInt(s.manual[i])} (${pct(s.votes[i] ? s.manual[i] / s.votes[i] : null)})`) + row('⚡ Votos rápidos', fmtInt(s.fast[i])) + row('Urnas abertas', fmtInt(s.open[i])));
}

// ---------------------------------------------------------------- controls
function bindUI() {
  const seg = (sel, attr, fn) => document.querySelectorAll(`${sel} button`).forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll(`${sel} button`).forEach(x => x.classList.toggle('on', x === b)); fn(b.dataset[attr]);
  }));
  seg('#metric-seg', 'metric', v => { S.metric = v; if (S.mode === 'count') setMode('vote'); render(); });
  seg('#mode-seg', 'mode', v => { S.mode = v; render(); });
  document.querySelectorAll('.tl-controls .seg:first-child button').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.tl-controls .seg:first-child button').forEach(x => x.classList.toggle('on', x === b)); S.speed = +b.dataset.speed;
  }));
  $('#chip-manual').addEventListener('click', e => { S.manualOnly = !S.manualOnly; e.currentTarget.setAttribute('aria-pressed', S.manualOnly); render(); });
  $('#chip-fast').addEventListener('click', e => { S.fastOverlay = !S.fastOverlay; e.currentTarget.setAttribute('aria-pressed', S.fastOverlay); render(); });
  $('#btn-about').addEventListener('click', () => $('#about').showModal());
  $('#tl-play').addEventListener('click', togglePlay);
  document.addEventListener('keydown', e => { if (e.code === 'Space' && !['INPUT', 'BUTTON'].includes(e.target.tagName)) { e.preventDefault(); togglePlay(); } });
}
function setMode(m) { S.mode = m; document.querySelectorAll('#mode-seg button').forEach(x => x.classList.toggle('on', x.dataset.mode === m)); }

let playT = 0;
function togglePlay() {
  S.playing = !S.playing;
  $('#tl-play-icon').setAttribute('d', S.playing ? 'M7 5h4v14H7zM13 5h4v14h-4z' : 'M8 5v14l11-7z');
  $('#tl-play').setAttribute('aria-label', S.playing ? 'Pausar' : 'Reproduzir');
  if (S.playing) {
    if (S.t >= M.time.end) timeline.set(M.time.start);
    playT = performance.now(); requestAnimationFrame(step);
  } else render();
}
function step(now) {
  if (!S.playing) return;
  const dt = (now - playT) / 1000; playT = now;
  timeline.set(S.t + dt * S.speed * 60);
  if (S.t >= M.time.end) { togglePlay(); return; }
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- about
function buildAbout() {
  const src = M.sources.map(s => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>${s.sha512 ? `<br>SHA-512: <code>${esc(s.sha512)}</code>` : ''}${s.note ? `<br>${esc(s.note)}` : ''}</li>`).join('');
  const mk = M.markers.map(m => `<li><b>${esc(m.label)} (${hhmmss(m.t)})</b>: ${esc(m.desc)}</li>`).join('');
  const B = M.fast_bins;
  $('#about-body').innerHTML = `
    <p><b>Princípio:</b> este site mostra os arquivos públicos do TSE como foram publicados. Nada é estimado, ponderado ou corrigido. As listas e destaques apenas ordenam números; a interpretação é sua.</p>
    <h4>O que os dados permitem — e o que não permitem</h4>
    <ul>
      <li>O <b>log da urna</b> registra, com horário, cada eleitor habilitado (por digital ou pelo mesário) e cada voto computado. <b>Não registra em quem</b> foi o voto.</li>
      <li>O <b>RDV</b> guarda os votos embaralhados, de propósito, para que não possam ser ligados à ordem dos eleitores. Por isso o mapa <b>não</b> fica vermelho/azul durante a votação: nesse período ele mostra atividade (comparecimento, votos sem biometria, votos rápidos) numa escala neutra.</li>
      <li>As cores de candidato aparecem apenas na <b>apuração</b>: cada urna é somada no horário em que o TSE recebeu seu Boletim de Urna.</li>
      <li>Os horários dos logs são os do relógio de cada urna, convertidos para o horário de Brasília.</li>
    </ul>
    <h4>Marcos da linha do tempo</h4><ul>${mk}</ul>
    <h4>Votos rápidos (critério ajustável)</h4>
    <p>Um voto sem biometria é marcado como rápido quando cumpre os três limites escolhidos: (1) tempo das leituras de digital até a urna pedir os dados pessoais (opções: ${B.fp.map(v => v ?? 'qualquer').join(', ')} s); (2) tempo até a digital do mesário liberar o eleitor (${B.rel.map(v => v ?? 'qualquer').join(', ')} s); (3) tempo da habilitação até o voto computado (${B.vote.map(v => v ?? 'qualquer').join(', ')} s). Para comparação, o site mostra sempre a mesma medida (3) entre eleitores identificados pela digital.</p>
    <h4>Verificação</h4>
    <p>Cada contagem de votos e de "não habilitados por biometria" extraída dos logs foi conferida contra o Boletim de Urna da mesma seção. ${esc(M.validation || '')}</p>
    ${(M.discrepancies || []).length ? `<p><b>Urnas em que o log difere do BU:</b></p><ul>${M.discrepancies.map(d => `<li>${esc(d.uf)} · zona ${esc(d.zona)}, seção ${esc(d.secao)}: BU ${d.bu_votes} votos / ${d.bu_manual} sem biometria; log ${d.log_votes} / ${d.log_manual}. ${esc(d.note)}</li>`).join('')}</ul>` : ''}
    <h4>Privacidade</h4><p>Os logs contêm o número do título de mesários. O site não publica esses números.</p>
    <h4>Fontes</h4><ul>${src}</ul>
    <p class="note">Gerado em ${esc(M.generated)}. Código e método: pasta <code>pipeline/</code> do repositório.</p>`;
}
