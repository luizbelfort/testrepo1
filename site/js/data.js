// Loading and time-aware aggregation. All numbers shown on the site come from these functions,
// computed from the TSE files exactly as published (see pipeline/).

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

function prefix(arr) {
  const out = new Int32Array(arr.length + 1);
  for (let i = 0; i < arr.length; i++) out[i + 1] = out[i] + arr[i];
  return out;
}

export class StateData {
  constructor(manifest, raw) {
    this.M = manifest; this.raw = raw; this.uf = raw.uf;
    const m = raw.munis;
    this.nMun = m.ibge.length;
    this.munIndex = new Map(m.ibge.map((id, i) => [id, i]));
    this.cum = {
      votes: raw.series.votes.map(prefix),
      manual: raw.series.manual.map(prefix),
      nofp: raw.series.nofp.map(prefix),
    };
    // urnas, sorted views for fast "as of time t" scans
    const u = raw.urnas; this.u = u; this.nUrna = u.m.length;
    this.byRecv = [...Array(this.nUrna).keys()].sort((a, b) => u.recv[a] - u.recv[b]);
    this.urnasByMun = Array.from({ length: this.nMun }, () => []);
    for (let i = 0; i < this.nUrna; i++) this.urnasByMun[u.m[i]].push(i);
    this.fastCache = null;
    this.munFast = new Map();
  }

  bucketsDone(t) {
    const T = this.M.time;
    return Math.max(0, Math.min(T.vote_n, Math.floor((t - T.vote_t0) / T.vote_step)));
  }

  // Per-municipality fast counts (prefix over 10-minute buckets) for the given thresholds.
  fastPrefix(th) {
    const key = `${th.fp}|${th.rel}|${th.vote}`;
    if (this.fastCache?.key === key) return this.fastCache;
    const T = this.M.time, n = T.fast_n;
    const mk = () => Array.from({ length: this.nMun }, () => new Int32Array(n));
    const full = mk(), voteOnlyManual = mk(), voteOnlyBio = mk(), bioAll = mk();
    const F = this.raw.fast.manual;
    for (let i = 0; i < F.m.length; i++) {
      const okVote = F.vote[i] <= th.vote;
      if (okVote) voteOnlyManual[F.m[i]][F.tb[i]] += F.n[i];
      if (okVote && F.fp[i] <= th.fp && F.rel[i] <= th.rel) full[F.m[i]][F.tb[i]] += F.n[i];
    }
    const B = this.raw.fast.bio;
    for (let i = 0; i < B.m.length; i++) {
      bioAll[B.m[i]][B.tb[i]] += B.n[i];
      if (B.vote[i] <= th.vote) voteOnlyBio[B.m[i]][B.tb[i]] += B.n[i];
    }
    this.fastCache = {
      key,
      full: full.map(prefix), voteManual: voteOnlyManual.map(prefix),
      voteBio: voteOnlyBio.map(prefix), bioAll: bioAll.map(prefix),
    };
    return this.fastCache;
  }

  fastBucketsDone(t) {
    const T = this.M.time;
    return Math.max(0, Math.min(T.fast_n, Math.floor((t - T.vote_t0) / T.fast_step)));
  }

  // Everything for one municipality (or all, when idx is null) as of time t.
  snapshot(t, th) {
    const b = this.bucketsDone(t), fb = this.fastBucketsDone(t);
    const fp = this.fastPrefix(th);
    const u = this.u, n = this.nMun;
    const res = {
      votes: new Float64Array(n), manual: new Float64Array(n), nofp: new Float64Array(n),
      fast: new Float64Array(n), fastVoteManual: new Float64Array(n), fastVoteBio: new Float64Array(n), bioAll: new Float64Array(n),
      open: new Float64Array(n), closed: new Float64Array(n), counted: new Float64Array(n),
      lula: new Float64Array(n), flavio: new Float64Array(n), branco: new Float64Array(n), nulo: new Float64Array(n),
      countedComp: new Float64Array(n), countedManual: new Float64Array(n),
    };
    for (let i = 0; i < n; i++) {
      res.votes[i] = this.cum.votes[i][b]; res.manual[i] = this.cum.manual[i][b]; res.nofp[i] = this.cum.nofp[i][b];
      res.fast[i] = fp.full[i][fb]; res.fastVoteManual[i] = fp.voteManual[i][fb];
      res.fastVoteBio[i] = fp.voteBio[i][fb]; res.bioAll[i] = fp.bioAll[i][fb];
    }
    for (let k = 0; k < this.nUrna; k++) {
      const m = u.m[k];
      if (u.close[k] >= 0 && u.close[k] <= t) res.closed[m]++;
      else if (u.open[k] >= 0 && u.open[k] <= t) res.open[m]++;
    }
    for (const k of this.byRecv) {
      if (u.recv[k] > t) break;
      const m = u.m[k];
      res.counted[m]++; res.lula[m] += u.lula[k]; res.flavio[m] += u.flavio[k];
      res.branco[m] += u.branco[k]; res.nulo[m] += u.nulo[k];
      res.countedComp[m] += u.comp[k]; res.countedManual[m] += u.manual[k];
    }
    return res;
  }

  // Series (per vote bucket) for the selected municipalities, for charts and the timeline silhouette.
  seriesFor(munIdxs, key) {
    const N = this.M.time.vote_n, out = new Float64Array(N);
    const src = this.raw.series[key];
    for (const i of munIdxs) { const s = src[i]; for (let j = 0; j < N; j++) out[j] += s[j]; }
    return out;
  }

  async loadMunFast(ibge) {
    if (this.munFast.has(ibge)) return this.munFast.get(ibge);
    const p = getJSON(`data/${this.uf}/fast/${ibge}.json`);
    this.munFast.set(ibge, p);
    return p;
  }
}

export function sumOver(snap, idxs) {
  const keys = Object.keys(snap), out = {};
  for (const k of keys) { let s = 0; for (const i of idxs) s += snap[k][i]; out[k] = s; }
  return out;
}
