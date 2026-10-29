// Pure filter and aggregation code of the replica (no DOM access). It decodes the ticket arrays of replica.json
// and mirrors tools/reference.py: days counted from 2024-01-01, SLA outcomes per ticket by creation date,
// `Resolved` by the final resolution date, the backlog as open intervals in whole days, DAX-like blanks (null).
// tests/replica/model.test.mjs checks every view against tests/replica/expected.json.

export const TABS = ['overview', 'sla', 'teams', 'backlog'];
export const PAGE = 25;
export const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const NEVER = 1e9;
const DAY_MS = 86400000;
const EPOCH = Date.UTC(2024, 0, 1);

export function defaultState() {
  return {
    tab: 'overview',
    from: '2024-01',
    to: '2025-09',
    team: null,
    priorities: [],
    channel: null,
    cross: null,
    rankBy: 'Resolved',
  };
}

// ------------------------------------------------------------ dates and months

export function dayNumber(year, month, day) {
  return Math.round((Date.UTC(year, month - 1, day) - EPOCH) / DAY_MS);
}

export function dayLabel(n) {
  return new Date(EPOCH + n * DAY_MS).toISOString().slice(0, 10);
}

function monthParts(ym) {
  return [Number(ym.slice(0, 4)), Number(ym.slice(5, 7))];
}

export function monthStart(ym) {
  const [y, m] = monthParts(ym);
  return dayNumber(y, m, 1);
}

export function monthEnd(ym) {
  const [y, m] = monthParts(ym);
  return dayNumber(y, m + 1, 1) - 1;
}

export function monthsBetween(from, to) {
  const out = [];
  let [y, m] = monthParts(from);
  const [ly, lm] = monthParts(to);
  while (y < ly || (y === ly && m <= lm)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m === 13) [y, m] = [y + 1, 1];
  }
  return out;
}

export function monthLabel(ym) {
  const [y, m] = monthParts(ym);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

// The same day a year earlier; a month's last day moves to that month's last day (DAX DATEADD).
export function shiftYear(n, years) {
  const d = new Date(EPOCH + n * DAY_MS);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() + 1;
  const day = d.getUTCDate();
  const last = dayNumber(y, m + 1, 1) - 1 === n;
  if (last) return dayNumber(y + years, m + 1, 1) - 1;
  const target = dayNumber(y + years, m, day);
  return new Date(EPOCH + target * DAY_MS).getUTCMonth() + 1 === m ? target : dayNumber(y + years, m + 1, 1) - 1;
}

// A stored state may be stale or edited by hand: keep only values the replica knows.
export function normaliseState(raw, data) {
  const base = defaultState();
  if (!raw || typeof raw !== 'object') return base;
  const { dims, meta } = data;
  const months = monthsBetween(meta.firstMonth, meta.lastMonth);
  const pick = (list, allowed) => (Array.isArray(list) ? allowed.filter((v) => list.includes(v)) : []);
  const out = {
    tab: TABS.includes(raw.tab) ? raw.tab : base.tab,
    from: months.includes(raw.from) ? raw.from : base.from,
    to: months.includes(raw.to) ? raw.to : base.to,
    team: dims.teams.includes(raw.team) ? raw.team : null,
    priorities: pick(raw.priorities, dims.priorities),
    channel: dims.channels.includes(raw.channel) ? raw.channel : null,
    cross: null,
    rankBy: dims.rankBy.includes(raw.rankBy) ? raw.rankBy : base.rankBy,
  };
  if (out.from > out.to) [out.from, out.to] = [out.to, out.from];
  const c = raw.cross;
  if (c && typeof c === 'object') {
    const ok = {
      category: () => dims.categories.includes(c.value),
      priority: () => dims.priorities.includes(c.value),
      cell: () => dims.teams.includes(c.team) && dims.priorities.includes(c.priority),
      agent: () => Number.isInteger(c.value) && c.value >= 0 && c.value < dims.agents.length,
      bucket: () => dims.buckets.some((b) => b[0] === c.value),
    }[c.dim];
    if (ok && ok()) out.cross = c.dim === 'cell' ? { dim: 'cell', team: c.team, priority: c.priority } : { dim: c.dim, value: c.value };
  }
  return out;
}

// One line for the phone filter disclosure: "Jan 2024 – Sep 2025 · all teams · all priorities · all channels".
export function summary(state) {
  const range = state.from === state.to ? monthLabel(state.from) : `${monthLabel(state.from)} – ${monthLabel(state.to)}`;
  const priorities = state.priorities.length ? state.priorities.join(', ') : 'all priorities';
  return `${range} · ${state.team ?? 'all teams'} · ${priorities} · ${state.channel ?? 'all channels'}`;
}

// ------------------------------------------------------------ DAX-like arithmetic

export function sub(a, b) {
  if (a === null && b === null) return null;
  return (a ?? 0) - (b ?? 0);
}

export function div(a, b) {
  if (a === null || a === 0 || b === null || b === 0) return null;
  return a / b;
}

export function median(values) {
  if (!values.length) return null;
  const v = Float64Array.from(values).sort();
  const mid = v.length >> 1;
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

const byName = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// ------------------------------------------------------------ the model

export function createModel(data) {
  const { dims, meta, tickets: a } = data;
  const n = a.d.length;
  const lastDay = monthEnd(meta.lastMonth);
  const firstId = meta.firstId;
  const minute = new Int32Array(n);
  const day = new Int32Array(n);
  const team = new Int8Array(n);
  const priority = new Int8Array(n);
  const channel = new Int8Array(n);
  const category = new Int8Array(n);
  const status = new Int8Array(n);
  const frOutcome = new Int8Array(n);
  const resOutcome = new Int8Array(n);
  const csat = new Int8Array(n);
  const reopens = new Int8Array(n);
  const firstRes = new Int32Array(n);
  const finalRes = new Int32Array(n);
  const intervals = [];
  let at = 0;
  for (let i = 0; i < n; i += 1) {
    at += a.t[i];
    minute[i] = at;
    day[i] = Math.floor(at / 1440);
    const d = a.d[i];
    team[i] = Math.floor(d / 576) + 1;
    priority[i] = Math.floor(d / 144) % 4;
    channel[i] = Math.floor(d / 36) % 4;
    category[i] = Math.floor(d / 6) % 6;
    status[i] = d % 6;
    const q = a.q[i];
    frOutcome[i] = Math.floor(q / 54);
    resOutcome[i] = Math.floor(q / 18) % 3;
    csat[i] = Math.floor(q / 3) % 6;
    reopens[i] = q % 3;
    firstRes[i] = a.v[i] >= 0 ? day[i] + a.v[i] : -1;
    finalRes[i] = firstRes[i];
    intervals.push([i, day[i], firstRes[i] >= 0 ? firstRes[i] : NEVER]);
  }
  for (let k = 0; k < a.reopens.length; k += 3) {
    const [i, start, end] = [a.reopens[k], a.reopens[k + 1], a.reopens[k + 2]];
    intervals.push([i, day[i] + start, end >= 0 ? day[i] + end : NEVER]);
    if (end >= 0) finalRes[i] = Math.max(finalRes[i], day[i] + end);
  }
  const resolvedStatus = new Set([dims.statuses.indexOf('Resolved'), dims.statuses.indexOf('Closed')]);
  const openStatus = new Set(dims.openStatuses.map((s) => dims.statuses.indexOf(s)));
  for (let i = 0; i < n; i += 1) if (!resolvedStatus.has(status[i])) finalRes[i] = -1;
  const teamIndex = (name) => dims.teams.indexOf(name) + 1;
  const priorityIndex = (name) => dims.priorities.indexOf(name);

  // ------------------------------------------------------------ contexts

  function context(state, tab, { cross = true } = {}) {
    let teams = state.team ? new Set([teamIndex(state.team)]) : null;
    let priorities = state.priorities.length ? new Set(state.priorities.map(priorityIndex)) : null;
    const channels = state.channel ? new Set([dims.channels.indexOf(state.channel)]) : null;
    let categories = null;
    let agents = null;
    const c = cross && state.tab === tab ? state.cross : null;
    if (c && c.dim === 'category') categories = new Set([dims.categories.indexOf(c.value)]);
    if (c && (c.dim === 'priority' || c.dim === 'cell')) {
      const p = priorityIndex(c.dim === 'priority' ? c.value : c.priority);
      priorities = !priorities || priorities.has(p) ? new Set([p]) : new Set();
    }
    if (c && c.dim === 'cell') {
      const t = teamIndex(c.team);
      teams = !teams || teams.has(t) ? new Set([t]) : new Set();
    }
    if (c && c.dim === 'agent') agents = new Set([c.value]);
    const lo = Math.max(monthStart(state.from), 0);
    const hi = Math.min(monthEnd(state.to), lastDay);
    return { lo, hi, teams, priorities, channels, categories, agents };
  }

  const where = (ctx, changes) => ({ ...ctx, ...changes });

  function passes(ctx, i) {
    return (!ctx.teams || ctx.teams.has(team[i]))
      && (!ctx.priorities || ctx.priorities.has(priority[i]))
      && (!ctx.channels || ctx.channels.has(channel[i]))
      && (!ctx.categories || ctx.categories.has(category[i]))
      && (!ctx.agents || ctx.agents.has(a.a[i]));
  }

  function created(ctx) {
    const out = [];
    if (ctx.lo > ctx.hi) return out;
    for (let i = 0; i < n; i += 1) if (day[i] >= ctx.lo && day[i] <= ctx.hi && passes(ctx, i)) out.push(i);
    return out;
  }

  function resolvedCount(ctx) {
    let count = 0;
    if (ctx.lo > ctx.hi) return null;
    for (let i = 0; i < n; i += 1) if (finalRes[i] >= ctx.lo && finalRes[i] <= ctx.hi && passes(ctx, i)) count += 1;
    return count || null;
  }

  function activeAgents(ctx) {
    const seen = new Set();
    if (ctx.lo > ctx.hi) return null;
    for (let i = 0; i < n; i += 1) if (finalRes[i] >= ctx.lo && finalRes[i] <= ctx.hi && passes(ctx, i)) seen.add(a.a[i]);
    return seen.size || null;
  }

  // Tickets open at the end of day `d` with their age in calendar days, oldest first (ties by ticket id).
  function openAt(ctx, d) {
    const out = [];
    for (const [i, start, end] of intervals) if (start <= d && d < end && passes(ctx, i)) out.push([i, d - day[i]]);
    out.sort((x, y) => y[1] - x[1] || x[0] - y[0]);
    return out;
  }

  // Backlog at the end of every day from 2024-01-01 to the as-of date.
  function backlogDays(ctx) {
    const change = new Int32Array(lastDay + 2);
    for (const [i, start, end] of intervals) {
      if (!passes(ctx, i)) continue;
      change[start] += 1;
      change[Math.min(end, lastDay + 1)] -= 1;
    }
    const out = new Int32Array(lastDay + 1);
    let level = 0;
    for (let d = 0; d <= lastDay; d += 1) {
      level += change[d];
      out[d] = level;
    }
    return out;
  }

  function backlog(ctx, d) {
    if (d < 0) return null;
    let any = false;
    for (let i = 0; i < n && day[i] <= d; i += 1) if (passes(ctx, i)) { any = true; break; }
    return any ? openAt(ctx, d).length : null;
  }

  function hours(rows, values) {
    const v = [];
    for (const i of rows) if (values[i] >= 0) v.push(values[i]);
    const m = median(v);
    return m === null ? null : m / 60;
  }

  function metPercent(rows, outcome) {
    let met = 0;
    let breached = 0;
    for (const i of rows) {
      if (outcome[i] === 0) met += 1;
      else if (outcome[i] === 1) breached += 1;
    }
    return div(met, met + breached);
  }

  function measure(name, ctx) {
    if (name === 'Resolved') return resolvedCount(ctx);
    if (name === 'Active agents') return activeAgents(ctx);
    if (name === 'Tickets per agent') return div(resolvedCount(ctx), activeAgents(ctx));
    if (name === 'Backlog') return ctx.lo > ctx.hi ? null : backlog(ctx, ctx.hi);
    const rows = created(ctx);
    if (name === 'Created') return rows.length || null;
    if (name === 'Median first response (h)') return hours(rows, a.f);
    if (name === 'Median resolution (h)') return hours(rows, a.r);
    if (name === 'SLA first response met %') return metPercent(rows, frOutcome);
    if (name === 'SLA resolution met %') return metPercent(rows, resOutcome);
    if (name === 'Breaches') return rows.filter((i) => frOutcome[i] === 1 || resOutcome[i] === 1).length || null;
    if (name === 'Open breaches now') {
      return rows.filter((i) => (frOutcome[i] === 1 || resOutcome[i] === 1) && openStatus.has(status[i])).length || null;
    }
    if (name === 'Reopen rate') {
      return div(rows.filter((i) => reopens[i] > 0).length, rows.filter((i) => firstRes[i] >= 0).length);
    }
    const answered = rows.filter((i) => csat[i] > 0);
    if (name === 'CSAT responses') return answered.length || null;
    if (name === 'CSAT average') return answered.length ? answered.reduce((s, i) => s + csat[i], 0) / answered.length : null;
    if (name === 'CSAT response rate') return div(answered.length, rows.filter((i) => resolvedStatus.has(status[i])).length);
    throw new Error(`unknown measure ${name}`);
  }

  const SNAPSHOT = new Set(['Backlog']);
  const ABSOLUTE = new Set(['Median first response (h)', 'SLA resolution met %', 'CSAT average']);

  // A KPI tile with the same months a year earlier; n/a (null) when that year is not wholly in the data.
  function tile(name, ctx) {
    const value = measure(name, ctx);
    const edge = SNAPSHOT.has(name) ? ctx.hi : ctx.lo;
    let py = null;
    if (ctx.lo <= ctx.hi && shiftYear(edge, -1) >= 0) {
      py = measure(name, where(ctx, { lo: Math.max(shiftYear(ctx.lo, -1), 0), hi: shiftYear(ctx.hi, -1) }));
    }
    let delta = null;
    if (value !== null && py !== null) delta = ABSOLUTE.has(name) ? value - py : value === py ? 0 : div(value - py, py);
    return { value, py, delta };
  }

  const inMonth = (ctx, ym) => where(ctx, { lo: monthStart(ym), hi: Math.min(monthEnd(ym), lastDay) });
  const table = (rows) => ({ count: rows.length, ids: [...rows].sort((x, y) => y - x).slice(0, PAGE).map((i) => firstId + i) });

  // ------------------------------------------------------------ tab views

  function overview(state) {
    const ctx = context(state, 'overview');
    const base = context(state, 'overview', { cross: false });
    const tiles = {
      created: tile('Created', ctx),
      resolved: tile('Resolved', ctx),
      backlog: tile('Backlog', ctx),
      medianFr: tile('Median first response (h)', ctx),
      resMet: tile('SLA resolution met %', ctx),
      csat: tile('CSAT average', ctx),
    };
    const days = backlogDays(ctx);
    const months = monthsBetween(state.from, state.to).map((ym) => [
      ym,
      measure('Created', inMonth(ctx, ym)),
      measure('Resolved', inMonth(ctx, ym)),
      days[Math.min(monthEnd(ym), lastDay)],
    ]);
    const categories = dims.categories.map((c, k) => [c, measure('Created', where(base, { categories: new Set([k]) }))]);
    const rows = created(ctx);
    const heatmap = new Array(7 * 24).fill(0);
    for (const i of rows) heatmap[(day[i] % 7) * 24 + Math.floor((minute[i] % 1440) / 60)] += 1;
    return { tiles, months, categories, heatmap, table: table(rows) };
  }

  function sla(state) {
    const ctx = context(state, 'sla');
    const base = context(state, 'sla', { cross: false });
    const tiles = {
      frMet: measure('SLA first response met %', ctx),
      resMet: measure('SLA resolution met %', ctx),
      breaches: measure('Breaches', ctx),
      openBreaches: measure('Open breaches now', ctx),
      medianRes: measure('Median resolution (h)', ctx),
    };
    const shown = dims.priorities.filter((p, k) => !base.priorities || base.priorities.has(k));
    const teams = dims.teams.filter((t, k) => !base.teams || base.teams.has(k + 1));
    const priorities = shown.map((p) => {
      const sub = where(base, { priorities: new Set([priorityIndex(p)]) });
      return [p, measure('SLA first response met %', sub), measure('SLA resolution met %', sub)];
    });
    const matrix = [];
    for (const t of teams) {
      for (const p of shown) {
        const sub = where(base, { teams: new Set([teamIndex(t)]), priorities: new Set([priorityIndex(p)]) });
        matrix.push([t, p, measure('SLA resolution met %', sub)]);
      }
    }
    const months = monthsBetween(state.from, state.to).map((ym) => [
      ym,
      measure('SLA first response met %', inMonth(ctx, ym)),
      measure('SLA resolution met %', inMonth(ctx, ym)),
    ]);
    const rows = created(ctx);
    const breaches = rows.filter((i) => frOutcome[i] === 1 || resOutcome[i] === 1);
    return { tiles, priorities, matrix, months, breaches: table(breaches), table: table(rows) };
  }

  // The agent scorecard: one row per agent (0 = Unassigned) with any value, the ranking value of `rankBy` for agents
  // with at least meta.rankMinCreated created tickets, and its dense rank.
  function agentRows(ctx, rankBy) {
    const rows = [];
    for (let id = 0; id < dims.agents.length; id += 1) {
      const sub = where(ctx, { agents: new Set([id]) });
      const v = {
        Created: measure('Created', sub),
        Resolved: measure('Resolved', sub),
        'Median resolution (h)': measure('Median resolution (h)', sub),
        'SLA resolution met %': measure('SLA resolution met %', sub),
        'SLA first response met %': measure('SLA first response met %', sub),
        'Reopen rate': measure('Reopen rate', sub),
        'CSAT average': measure('CSAT average', sub),
        'CSAT responses': measure('CSAT responses', sub),
      };
      const ranking = (v.Created ?? 0) >= meta.rankMinCreated ? v[rankBy] : null;
      if (Object.entries(v).some(([k, x]) => k !== 'Created' && x !== null)) rows.push({ id, ranking, ...v });
    }
    const ranked = [...new Set(rows.filter((r) => r.ranking !== null).map((r) => r.ranking))].sort((x, y) => y - x);
    for (const r of rows) r.rank = r.ranking === null ? null : ranked.indexOf(r.ranking) + 1;
    return rows;
  }

  const agentName = (id) => dims.agents[id][0];

  function teams(state) {
    const ctx = context(state, 'teams');
    const base = context(state, 'teams', { cross: false });
    const tiles = {
      resolved: measure('Resolved', base),
      activeAgents: measure('Active agents', base),
      perAgent: measure('Tickets per agent', base),
      reopenRate: measure('Reopen rate', base),
      csat: measure('CSAT average', base),
      csatRate: measure('CSAT response rate', base),
    };
    let rows = agentRows(base, state.rankBy);
    const ranking = rows
      .filter((r) => r.ranking !== null)
      .map((r) => [r.id, r.ranking])
      .sort((x, y) => y[1] - x[1] || byName(agentName(x[0]), agentName(y[0])));
    if (ctx.agents) rows = rows.filter((r) => ctx.agents.has(r.id));
    rows.sort((x, y) => (x.rank === null) - (y.rank === null) || (x.rank ?? 0) - (y.rank ?? 0) || byName(agentName(x.id), agentName(y.id)));
    const scorecard = rows.map((r) => [
      r.id, r.rank, r.Resolved, r['Median resolution (h)'], r['SLA resolution met %'], r['SLA first response met %'],
      r['Reopen rate'], r['CSAT average'], r['CSAT responses'],
    ]);
    const shown = [1, 2, 3, 4].filter((t) => !base.teams || base.teams.has(t));
    const perAgent = monthsBetween(state.from, state.to).map((ym) => [
      ym,
      shown.map((t) => measure('Tickets per agent', where(inMonth(base, ym), { teams: new Set([t]) }))),
    ]);
    const scores = [0, 0, 0, 0, 0];
    for (const i of created(base)) if (csat[i] > 0) scores[csat[i] - 1] += 1;
    return { tiles, ranking, scorecard, perAgent, csat: scores, table: table(created(ctx)) };
  }

  function bucketOf(age) {
    return dims.buckets.find(([, lo, hi]) => lo <= age && age <= hi)[0];
  }

  function backlogView(state) {
    const ctx = context(state, 'backlog');
    const d = ctx.hi;
    const open = ctx.lo > ctx.hi ? [] : openAt(ctx, d);
    const ages = open.map(([, age]) => age);
    const now = backlog(ctx, d);
    const tiles = {
      backlog: now,
      change30: now === null ? null : now - (d - 30 >= 0 ? openAt(ctx, d - 30).length : 0),
      over7: ages.filter((x) => x >= 8).length || null,
      oldest: ages.length ? Math.max(...ages) : null,
    };
    const series = Array.from(backlogDays(ctx).slice(ctx.lo, d + 1));
    const statuses = dims.openStatuses.map((s) => {
      const k = dims.statuses.indexOf(s);
      let count = 0;
      for (let i = 0; i < n; i += 1) if (status[i] === k && passes(ctx, i)) count += 1;
      return [s, count];
    });
    const names = dims.buckets.map((b) => b[0]);
    const withBucket = open.map(([i, age]) => [i, age, bucketOf(age)]);
    const buckets = names.map((b) => [b, withBucket.filter((r) => r[2] === b).length]);
    const shown = [1, 2, 3, 4].filter((t) => !ctx.teams || ctx.teams.has(t));
    const byTeam = shown.map((t) => [dims.teams[t - 1], names.map((b) => withBucket.filter((r) => team[r[0]] === t && r[2] === b).length)]);
    const c = state.tab === 'backlog' ? state.cross : null;
    const listed = c && c.dim === 'bucket' ? withBucket.filter((r) => r[2] === c.value) : withBucket;
    return {
      snapshot: dayLabel(d),
      tiles,
      days: series,
      statuses,
      buckets,
      teams: byTeam,
      oldest: listed.slice(0, PAGE).map(([i, age]) => [firstId + i, age]),
      table: table(listed.map(([i]) => i)),
    };
  }

  const views = { overview, sla, teams, backlog: backlogView };

  // ------------------------------------------------------------ the ticket table

  // The tickets behind a tab's ticket table (indexes), in the tab's context.
  function rowsOf(state, tab = state.tab) {
    const ctx = context(state, tab);
    if (tab !== 'backlog') return created(ctx);
    const c = state.tab === 'backlog' ? state.cross : null;
    const open = ctx.lo > ctx.hi ? [] : openAt(ctx, ctx.hi);
    return open.filter(([, age]) => !c || c.dim !== 'bucket' || bucketOf(age) === c.value).map(([i]) => i);
  }

  function ticket(i) {
    const customer = a.c[i];
    const s = a.s[i];
    const id = firstId + i;
    const at = new Date(EPOCH + minute[i] * 60000).toISOString();
    return {
      index: i,
      id,
      number: `QS-${id}`,
      created: `${at.slice(0, 10)} ${at.slice(11, 16)}`,
      createdDay: day[i],
      team: dims.teams[team[i] - 1],
      agent: agentName(a.a[i]),
      priority: dims.priorities[priority[i]],
      channel: dims.channels[channel[i]],
      category: dims.categories[category[i]],
      status: dims.statuses[status[i]],
      subject: dims.subjects[category[i]][Math.floor(s / 8)].replace('{module}', dims.modules[s % 8]),
      customer: `Account C${String(customer + 1).padStart(4, '0')}`,
      tier: dims.tiers[dims.customerTiers[customer]],
      frHours: a.f[i] >= 0 ? a.f[i] / 60 : null,
      resHours: a.r[i] >= 0 ? a.r[i] / 60 : null,
      frOutcome: dims.outcomes[frOutcome[i]],
      resOutcome: dims.outcomes[resOutcome[i]],
      csat: csat[i] || null,
      reopens: reopens[i],
      resolved: finalRes[i] >= 0 ? dayLabel(finalRes[i]) : null,
    };
  }

  // Search over ticket number and subject, case-insensitive.
  function search(rows, text) {
    const q = String(text ?? '').trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((i) => `qs-${firstId + i}`.includes(q) || ticket(i).subject.toLowerCase().includes(q));
  }

  const SORT_KEYS = ['number', 'created', 'priority', 'team', 'agent', 'category', 'status', 'subject'];

  function sortRows(rows, key = 'number', dir = 'desc') {
    if (!SORT_KEYS.includes(key)) key = 'number';
    const sign = dir === 'asc' ? 1 : -1;
    const value = (i) => (key === 'number' || key === 'created' ? i : ticket(i)[key]);
    return [...rows].sort((x, y) => {
      const vx = value(x);
      const vy = value(y);
      return sign * (vx < vy ? -1 : vx > vy ? 1 : 0) || y - x;
    });
  }

  return {
    data,
    lastDay,
    views,
    view: (state, tab = state.tab) => views[tab](state),
    rows: rowsOf,
    ticket,
    search,
    sortRows,
    context,
    agentName,
    bucketOf,
    sortKeys: SORT_KEYS,
  };
}
