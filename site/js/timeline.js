import { hhmm } from './scales.js?v=20261103d';

// The wide scrubber at the top. Owns no data logic: it draws context series handed to it
// and reports the chosen time through onChange(t).
export class Timeline {
  constructor({ track, canvas, markersEl, handle, manifest, onChange }) {
    Object.assign(this, { track, canvas, markersEl, handle, M: manifest, onChange });
    this.t0 = manifest.time.start; this.t1 = manifest.time.end;
    this.t = manifest.time.vote_t0;
    this.context = { votes: null, recv: null };
    this.buildMarkers();
    this.bind();
    new ResizeObserver(() => this.draw()).observe(track);
  }

  x(t) { return ((t - this.t0) / (this.t1 - this.t0)) * this.track.clientWidth; }
  tAt(px) {
    const f = Math.max(0, Math.min(1, px / this.track.clientWidth));
    return Math.round(this.t0 + f * (this.t1 - this.t0));
  }

  set(t, silent = false) {
    this.t = Math.max(this.t0, Math.min(this.t1, Math.round(t)));
    this.handle.style.left = `${this.x(this.t)}px`;
    this.track.setAttribute('aria-valuenow', String(this.t));
    this.track.setAttribute('aria-valuetext', hhmm(this.t));
    if (!silent) this.onChange(this.t);
  }

  setContext(ctx) { this.context = ctx; this.draw(); }

  buildMarkers() {
    this.markersEl.innerHTML = '';
    const ms = [...this.M.markers].sort((a, b) => a.t - b.t);
    let lastX = -1e9, row = 0;
    this.markerEls = ms.map(m => {
      const el = document.createElement('div');
      el.className = 'tl-marker';
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = `${m.label} · ${hhmm(m.t)}`; b.title = m.desc || '';
      b.addEventListener('click', e => { e.stopPropagation(); this.set(m.t); });
      el.appendChild(b); this.markersEl.appendChild(el);
      return { m, el };
    });
    this.layoutMarkers = () => {
      // greedy row assignment on real label extents; labels near the edges are aligned inward
      const W = this.track.clientWidth, rows = [[], [], []];
      for (const { m, el } of this.markerEls) {
        const x = this.x(m.t); el.style.left = `${x}px`;
        const b = el.firstChild;
        b.textContent = `${W < 760 && m.short ? m.short : m.label} · ${hhmm(m.t)}`;
        const w = b.offsetWidth || 120;
        let shift = -w / 2;
        if (x + shift < 4) shift = 4 - x;
        if (x + shift + w > W - 4) shift = W - 4 - w - x;
        b.style.transform = `translateX(${shift}px)`;
        const span = [x + shift - 6, x + shift + w + 6];
        let r = rows.findIndex(row => row.every(([a, c]) => span[1] < a || span[0] > c));
        if (r < 0) r = 2;
        rows[r].push(span);
        b.style.top = `${6 + r * 24}px`;
      }
    };
  }

  bind() {
    let dragging = false;
    const fromEvent = e => {
      const r = this.track.getBoundingClientRect();
      this.set(this.tAt(e.clientX - r.left));
    };
    this.track.addEventListener('pointerdown', e => {
      if (e.target.closest('button')) return;
      dragging = true; this.track.setPointerCapture(e.pointerId); fromEvent(e);
    });
    this.track.addEventListener('pointermove', e => { if (dragging) fromEvent(e); });
    this.track.addEventListener('pointerup', () => { dragging = false; });
    this.track.addEventListener('wheel', e => {
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (!d) return;
      e.preventDefault();
      this.set(this.t + Math.sign(d) * Math.max(60, Math.abs(d) * 6));
    }, { passive: false });
    this.track.addEventListener('keydown', e => {
      const step = e.shiftKey ? 600 : 60;
      if (e.key === 'ArrowRight') this.set(this.t + step);
      else if (e.key === 'ArrowLeft') this.set(this.t - step);
      else if (e.key === 'Home') this.set(this.t0);
      else if (e.key === 'End') this.set(this.t1);
      else return;
      e.preventDefault();
    });
  }

  draw() {
    const c = this.canvas, dpr = window.devicePixelRatio || 1;
    const W = this.track.clientWidth, H = this.track.clientHeight;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const base = H - 18, top = 54, M = this.M;
    const mk = Object.fromEntries(M.markers.map(m => [m.key, m.t]));

    // phase bands
    const band = (a, b, col) => { if (a == null || b == null) return; g.fillStyle = col; g.fillRect(this.x(a), 0, this.x(b) - this.x(a), H); };
    band(mk.open, mk.close_regular, 'rgba(27,175,122,0.06)');
    band(mk.ext_start, mk.ext_end, 'rgba(250,178,25,0.08)');
    band(mk.first_bu, mk.last_bu, 'rgba(240,239,236,0.04)');

    // votes per bucket (neutral teal silhouette)
    const v = this.context.votes;
    if (v) {
      const T = M.time, mx = Math.max(1, ...v);
      g.beginPath(); g.moveTo(this.x(T.vote_t0), base);
      for (let i = 0; i < v.length; i++) {
        const t = T.vote_t0 + (i + 0.5) * T.vote_step;
        g.lineTo(this.x(t), base - (v[i] / mx) * (base - top));
      }
      g.lineTo(this.x(T.vote_t0 + v.length * T.vote_step), base); g.closePath();
      g.fillStyle = 'rgba(27,175,122,0.35)'; g.fill();
      g.strokeStyle = '#1baf7a'; g.lineWidth = 1.5; g.stroke();
    }
    // BU receipts per minute (neutral light bars)
    const r = this.context.recv;
    if (r) {
      const mx = Math.max(1, ...r.counts);
      g.fillStyle = 'rgba(240,239,236,0.55)';
      for (let i = 0; i < r.counts.length; i++) {
        if (!r.counts[i]) continue;
        const x = this.x(r.t0 + i * r.step), w = Math.max(1, this.x(r.t0 + (i + 1) * r.step) - x - 0.5);
        const h = (r.counts[i] / mx) * (base - top);
        g.fillRect(x, base - h, w, h);
      }
    }
    // hour ticks
    g.fillStyle = '#8b8a84'; g.font = '11px "JetBrains Mono", monospace'; g.textAlign = 'center';
    const step = W < 700 ? 7200 : 3600;
    for (let t = Math.ceil(this.t0 / 3600) * 3600; t <= this.t1; t += step) {
      const x = this.x(t);
      g.fillRect(x, base, 1, 4);
      g.fillText(hhmm(t), x, H - 4);
    }
    g.fillStyle = '#2c2c31'; g.fillRect(0, base, W, 1);
    this.layoutMarkers();
    this.set(this.t, true);
  }
}
