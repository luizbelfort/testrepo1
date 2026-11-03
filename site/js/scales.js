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
  uncounted: '#34343a',
  mid: '#e4e2dc',
  amber: '#fab219',
  lula: '#e5484d',
  flavio: '#3987e5',
};

// Darker always means MORE: light = little / close to a tie, dark = a lot / a large lead.
export const seq = ramp(['#e3f4ec', '#a6dcc4', '#4fb38d', '#1a7a5c', '#0b4434']);
const redArm = ramp(['#e4e2dc', '#f0b3ae', '#de5f5c', '#b0242b', '#6e0d16']);
const blueArm = ramp(['#e4e2dc', '#b4cbee', '#5a91de', '#2257b5', '#0e2f6b']);

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
  turnoutManual: { max: 0.15, fmt: v => pct(v, 0), title: 'Votos sem biometria (falha + não pedida) até o horário ÷ eleitores aptos' },
  manual: { max: 0.3, fmt: v => pct(v, 0), title: 'Votos sem biometria (falha na leitura + urna não pediu) ÷ votos' },
  fast: { max: 0.1, fmt: v => pct(v, 0), title: 'Votos rápidos ÷ votos com falha na leitura da digital' },
  late: { max: 0.002, fmt: v => `${Math.round(v * 10000).toLocaleString('pt-BR')}`, title: 'Votos depois do corte, por 10 mil votos do município' },
  manualCount: { max: 0.3, fmt: v => pct(v, 0), title: 'Votos sem biometria (falha + não pedida) ÷ votos, urnas apuradas' },
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
