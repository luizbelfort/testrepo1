import { hhmm, fmtInt } from './scales.js';

// Small single-series area chart with a time cursor and a hover tooltip.
// One measure per chart (no dual axes): different measures get separate charts.
export function areaChart(container, { series, t0, step, cursor, color, label, unit = 'votos' }) {
  container.innerHTML = '';
  const canvas = document.createElement('canvas'); container.appendChild(canvas);
  const tip = document.createElement('div'); tip.className = 'tooltip'; tip.hidden = true; container.appendChild(tip);
  const draw = (hoverI = null) => {
    const dpr = window.devicePixelRatio || 1, W = container.clientWidth, H = container.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const g = canvas.getContext('2d'); g.scale(dpr, dpr);
    const n = series.length, mx = Math.max(1, ...series), base = H - 14, top = 6;
    const X = i => (i / n) * W, Y = v => base - (v / mx) * (base - top);
    g.strokeStyle = '#2c2c31'; g.lineWidth = 1; g.beginPath(); g.moveTo(0, base + 0.5); g.lineTo(W, base + 0.5); g.stroke();
    g.beginPath(); g.moveTo(0, base);
    for (let i = 0; i < n; i++) g.lineTo(X(i + 0.5), Y(series[i]));
    g.lineTo(W, base); g.closePath();
    g.fillStyle = color + '40'; g.fill(); g.strokeStyle = color; g.lineWidth = 2;
    g.beginPath(); for (let i = 0; i < n; i++) (i ? g.lineTo : g.moveTo).call(g, X(i + 0.5), Y(series[i])); g.stroke();
    // cursor (current time)
    const ci = (cursor - t0) / step;
    if (ci >= 0 && ci <= n) { g.fillStyle = '#f0efec'; g.fillRect(X(ci), top - 4, 1.5, base - top + 4); }
    // axis labels: first/last hour
    g.fillStyle = '#8b8a84'; g.font = '10px "JetBrains Mono", monospace';
    g.textAlign = 'left'; g.fillText(hhmm(t0), 0, H - 2);
    g.textAlign = 'right'; g.fillText(hhmm(t0 + n * step), W, H - 2);
    g.textAlign = 'right'; g.fillText(`máx ${fmtInt(mx)}`, W, 10);
    if (hoverI != null) {
      g.fillStyle = color; g.beginPath(); g.arc(X(hoverI + 0.5), Y(series[hoverI]), 4, 0, 7); g.fill();
      g.strokeStyle = '#121214'; g.lineWidth = 2; g.stroke();
    }
  };
  canvas.addEventListener('pointermove', e => {
    const r = canvas.getBoundingClientRect(), i = Math.max(0, Math.min(series.length - 1, Math.floor(((e.clientX - r.left) / r.width) * series.length)));
    draw(i);
    tip.hidden = false;
    tip.innerHTML = `<div class="tt-title">${hhmm(t0 + i * step)}–${hhmm(t0 + (i + 1) * step)}</div><div class="tt-row">${label}<b>${fmtInt(series[i])} ${unit}</b></div>`;
    const x = e.clientX - r.left;
    tip.style.left = `${Math.min(r.width - 200, Math.max(0, x - 100))}px`; tip.style.top = `-56px`;
  });
  canvas.addEventListener('pointerleave', () => { tip.hidden = true; draw(); });
  draw();
}
