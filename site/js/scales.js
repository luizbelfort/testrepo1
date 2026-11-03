// Colour scales. Activity (voting day) uses ONE neutral hue (teal) so nothing during voting
// reads as red/blue. Red/blue is used only for counted results (diverging, grey midpoint).

const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const toHex = c => '#' + c.map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
function ramp(stops) {
  const cs = stops.map(hex);
  return t => {
    if (t == null || Number.isNaN(t)) return null;
    t = Math.max(0, Math.min(1, t));
    const x = t * (cs.length - 1), i = Math.min(cs.length - 2, Math.floor(x)), f = x - i;
    return toHex(cs[i].map((v, k) => v + (cs[i + 1][k] - v) * f));
  };
}

export const COLORS = {
  noData: '#18181b',
  uncounted: '#26262a',
  mid: '#383835',
  amber: '#fab219',
  lula: '#e5484d',
  flavio: '#3987e5',
};

export const seq = ramp(['#16201d', '#124d3f', '#168a63', '#3fc792', '#b8f0d6']);
const redArm = ramp(['#383835', '#6b2b2c', '#b83a3d', '#f26b6d']);
const blueArm = ramp(['#383835', '#24456f', '#2f6fbd', '#5aa2f5']);

// share = Lula share of valid votes (0..1). Full colour is reached at a 60-point margin (80/20).
export const DIVERGING_SPAN = 0.3;
export function diverging(share) {
  if (share == null) return null;
  const d = share - 0.5;
  return d >= 0 ? redArm(d / DIVERGING_SPAN) : blueArm(-d / DIVERGING_SPAN);
}

// Fixed domains (not rescaled with time) so colours stay comparable across the whole timeline.
export const METRIC_DOMAINS = {
  turnout: { max: 0.9, fmt: v => pct(v, 0), title: 'Comparecimento até o horário (votos ÷ eleitores aptos)' },
  turnoutManual: { max: 0.15, fmt: v => pct(v, 0), title: 'Votos sem biometria até o horário ÷ eleitores aptos' },
  manual: { max: 0.2, fmt: v => pct(v, 0), title: 'Votos sem biometria ÷ votos até o horário' },
  fast: { max: 0.1, fmt: v => pct(v, 0), title: 'Votos rápidos ÷ votos sem biometria até o horário' },
  manualCount: { max: 0.2, fmt: v => pct(v, 0), title: 'Votos sem biometria ÷ votos (urnas já apuradas)' },
};

export const fmtInt = n => (n == null ? '—' : Math.round(n).toLocaleString('pt-BR'));
export function pct(v, d = 1) {
  if (v == null || !Number.isFinite(v)) return '—';
  return (v * 100).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) + '%';
}
export function hhmm(t) {
  if (t == null || t < 0) return '—';
  const day = Math.floor(t / 86400), s = t % 86400;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}${day ? ` (+${day}d)` : ''}`;
}
export function hhmmss(t) {
  if (t == null || t < 0) return '—';
  const s = t % 86400;
  return `${hhmm(t)}:${String(s % 60).padStart(2, '0')}`;
}
