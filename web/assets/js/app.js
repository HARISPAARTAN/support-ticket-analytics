// The replica's page code: state, filters, tabs, tiles, tables and charts. All numbers come from model.js (pure,
// tested against the Python reference) and are formatted with the kit's fmt helpers.
import { createFilterBus, createStore, fmt, initTabs, mountBanner, mountThemeToggle, renderKpi, renderTable } from '../../kit/kit.js';
import { registerThemes, sequential } from '../../kit/echarts-theme.js';
import * as charts from './charts.js';
import { PAGE, TABS, createModel, dayLabel, defaultState, monthLabel, monthStart, monthsBetween, normaliseState, summary } from './model.js';

const REPO = 'https://github.com/HARISPAARTAN/support-ticket-analytics';
const store = createStore('support-ticket-analytics');
const bus = createFilterBus();
const $ = (id) => document.getElementById(id);
const motionQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
const motion = () => !(motionQuery && motionQuery.matches);

let model;
let state;
let host;
let theme = 'dark';
const tables = {};
const barMax = {};
const cache = [];
const ticketOf = (i) => (cache[i] ??= model.ticket(i));

// ---------------------------------------------------------------- formatting

const int = (v) => fmt.int(v);
const pct = (v) => fmt.pct(v);
const hours = charts.hoursText;
const signedPct = (x) => `${x > 0 ? '+' : ''}${fmt.pct(x)}`;

function colours() {
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(`--${name}`).trim();
  return {
    text: token('text'),
    muted: token('muted'),
    border: token('border'),
    surface: token('surface'),
    surface2: token('surface-2'),
    accent: token('accent'),
    ok: token('ok'),
    warn: token('warn'),
    danger: token('danger'),
    chart: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => token(`chart-${n}`)),
    seq: [...sequential[theme]],
  };
}

// A KPI tile with its change against the same months a year earlier, worded like the report's text measures.
// `better` says which direction is good news (green); null keeps the change neutral.
function tileData(label, tile, show, { change = 'relative', better = 'up', caption = '' } = {}) {
  if (tile.delta === null || tile.delta === undefined) {
    return { label, value: show(tile.value), delta: { kind: 'neutral', text: 'vs PY: n/a' }, caption };
  }
  const text = {
    relative: () => signedPct(tile.delta),
    hours: () => `${fmt.signed(tile.delta, 2)} h`,
    pp: () => fmt.pp(tile.delta),
    plain: () => fmt.signed(tile.delta, 2),
  }[change]();
  const sign = Math.sign(tile.delta) * (better === 'down' ? -1 : 1);
  const kind = better === null || sign === 0 ? 'neutral' : sign > 0 ? 'up' : 'down';
  return { label, value: show(tile.value), delta: { kind, text: `vs PY: ${text}` }, caption, dir: Math.sign(tile.delta) };
}

// The kit colours a change by good (ok) or bad (danger) and draws ▲ or ▼ to match; for a measure where lower is
// better (backlog, response time) the arrow is set to the direction of the change, so a rise in red shows ▲.
function tiles(el, list) {
  el.replaceChildren(...list.map((data) => {
    const box = document.createElement('div');
    renderKpi(box, data);
    const mark = box.querySelector('.pf-kpi__delta > span');
    if (mark && data.dir) mark.textContent = data.dir > 0 ? '▲ ' : '▼ ';
    return box.firstElementChild;
  }));
}

// ---------------------------------------------------------------- state

function save() {
  const { tab, from, to, team, priorities, channel, rankBy } = state;
  store.save({ tab, from, to, team, priorities, channel, rankBy });
}

function update(changes) {
  state = { ...normaliseState({ ...state, ...changes }, model.data), cross: state.cross };
  save();
  render();
}

function tabFromHash() {
  const name = location.hash.replace('#', '');
  return TABS.includes(name) ? name : null;
}

// ---------------------------------------------------------------- filter bar

function buildFilters() {
  const months = monthsBetween(model.data.meta.firstMonth, model.data.meta.lastMonth);
  for (const id of ['month-from', 'month-to']) {
    $(id).replaceChildren(...months.map((ym) => new Option(monthLabel(ym), ym)));
  }
  $('month-from').addEventListener('change', (e) => update({ from: e.target.value }));
  $('month-to').addEventListener('change', (e) => update({ to: e.target.value }));
  const { teams, priorities, channels, rankBy } = model.data.dims;
  $('team').replaceChildren(new Option('All teams', ''), ...teams.map((t) => new Option(t, t)));
  $('team').addEventListener('change', (e) => update({ team: e.target.value || null }));
  $('channel').replaceChildren(new Option('All channels', ''), ...channels.map((c) => new Option(c, c)));
  $('channel').addEventListener('change', (e) => update({ channel: e.target.value || null }));
  $('priority-chips').replaceChildren(...priorities.map((p) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pf-chip';
    button.textContent = p;
    button.dataset.priority = p;
    button.addEventListener('click', () => {
      const chosen = state.priorities.includes(p) ? state.priorities.filter((x) => x !== p) : [...state.priorities, p];
      update({ priorities: chosen });
    });
    return button;
  }));
  $('rank-by').replaceChildren(...rankBy.map((r) => new Option(r, r)));
  $('rank-by').addEventListener('change', (e) => update({ rankBy: e.target.value }));
  $('reset').addEventListener('click', () => {
    store.clear();
    state = { ...defaultState(), tab: state.tab, cross: null };
    if (bus.get('cross')) bus.clear();
    else render();
  });
  $('filters-toggle').addEventListener('click', () => {
    const open = !$('filters').classList.contains('is-open');
    $('filters').classList.toggle('is-open', open);
    $('filters-toggle').setAttribute('aria-expanded', String(open));
  });
}

function crossText(c) {
  if (c.dim === 'cell') return ['team and priority', `${c.team} · ${c.priority}`];
  if (c.dim === 'agent') return ['agent', model.agentName(c.value)];
  return [c.dim, c.value];
}

function syncFilters() {
  $('month-from').value = state.from;
  $('month-to').value = state.to;
  $('team').value = state.team ?? '';
  $('channel').value = state.channel ?? '';
  $('rank-by').value = state.rankBy;
  for (const button of $('priority-chips').children) {
    button.setAttribute('aria-pressed', String(state.priorities.includes(button.dataset.priority)));
  }
  $('filter-summary').textContent = summary(state);
  const box = $('cross-chip');
  if (!state.cross) {
    box.className = 'xchip xchip--idle';
    box.textContent = 'none · click a bar or cell';
    return;
  }
  const [dim, value] = crossText(state.cross);
  box.className = 'xchip';
  const text = document.createElement('span');
  const strong = document.createElement('b');
  strong.textContent = value;
  text.append(document.createTextNode(`${dim}: `), strong);
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'xchip__clear';
  clear.textContent = '×';
  clear.setAttribute('aria-label', `Clear the cross-filter ${value}`);
  // The button is replaced by the re-render, so focus moves to the chip's container, which stays in the page.
  clear.addEventListener('click', () => {
    bus.clear('cross');
    box.focus();
  });
  box.replaceChildren(text, clear);
}

function toggleCross(value) {
  bus.toggle('cross', value);
}

// ---------------------------------------------------------------- tables

// Every cell carries its column name, which the stacked row cards below 640 px show (app.css).
function cell(label, content) {
  const span = document.createElement('span');
  span.className = 'cell';
  span.dataset.label = label;
  if (content !== null && typeof content === 'object' && 'nodeType' in content) span.append(content);
  else span.textContent = content === null || content === undefined ? '–' : String(content);
  return span;
}

function col(key, label, show = (v) => v, { align, sortable } = {}) {
  return { key, label, align, sortable, format: (value, row) => cell(label, show(value, row)) };
}

const num = (key, label, show) => col(key, label, show, { align: 'right' });

function table(name, el, options, sortKey, dir = 'desc') {
  if (!tables[name]) {
    tables[name] = renderTable(el, options);
    tables[name].sort(sortKey, dir);
  } else {
    tables[name].update(options.rows);
  }
  return tables[name];
}

// The scale is read on every cell, so it follows the rows of the latest render; the width never passes 100 %.
function dataBar(name, show) {
  return (value) => {
    const max = barMax[name];
    const box = document.createElement('span');
    box.className = 'dbar';
    const bar = document.createElement('i');
    bar.style.width = `${max > 0 ? Math.min(100, Math.max(0, (100 * (value ?? 0)) / max)) : 0}%`;
    const text = document.createElement('span');
    text.textContent = show(value);
    box.append(bar, text);
    return box;
  };
}

function ticketButton(id) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'tno';
  button.dataset.index = String(id - model.data.meta.firstId);
  button.textContent = `QS-${id}`;
  return button;
}

function subject(text) {
  const span = document.createElement('span');
  span.className = 'subject';
  span.title = text;
  span.textContent = text;
  return span;
}

const TICKET_COLUMNS = [
  col('id', 'Ticket', ticketButton),
  col('created', 'Created'),
  col('priority', 'Priority'),
  col('team', 'Team'),
  col('agent', 'Agent'),
  col('category', 'Category'),
  col('status', 'Status'),
  col('subject', 'Subject', subject),
];

function showDetail(index) {
  const t = ticketOf(index);
  const fields = [
    ['Subject', t.subject],
    ['Created', t.created],
    ['Status', t.status],
    ['Priority', t.priority],
    ['Team', t.team],
    ['Agent', t.agent],
    ['Channel', t.channel],
    ['Category', t.category],
    ['Customer', `${t.customer} (${t.tier})`],
    ['First response', `${hours(t.frHours)} · SLA ${t.frOutcome}`],
    ['Resolution', `${hours(t.resHours)} · SLA ${t.resOutcome}`],
    ['Resolved on', t.resolved ? fmt.date(t.resolved) : 'not resolved'],
    ['Reopened', `${int(t.reopens)} ${t.reopens === 1 ? 'time' : 'times'}`],
    ['CSAT', t.csat === null ? 'no response' : `${t.csat} of 5`],
  ];
  $('detail-title').textContent = `Ticket ${t.number}`;
  $('detail-fields').replaceChildren(...fields.flatMap(([label, value]) => {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    return [dt, dd];
  }));
  $('detail').showModal();
}

function renderTickets() {
  const indexes = model.search(model.rows(state), $('ticket-search').value);
  const rows = indexes.map(ticketOf);
  const what = state.tab === 'backlog' ? 'open at the snapshot' : 'created in the range';
  $('tickets-sub').textContent = `${int(rows.length)} tickets ${what} · 25 per page · search, sort, open a ticket`;
  table('tickets', $('table-tickets'), {
    caption: 'Tickets of this tab',
    pageSize: PAGE,
    emptyText: 'No ticket matches the search',
    columns: TICKET_COLUMNS,
    rows,
  }, 'id');
}

// ---------------------------------------------------------------- tabs

function renderOverview(c) {
  const view = model.view(state, 'overview');
  const t = view.tiles;
  tiles($('overview-tiles'), [
    tileData('Created', t.created, int, { better: null, caption: 'by creation date' }),
    tileData('Resolved', t.resolved, int, { caption: 'final resolutions' }),
    tileData('Backlog', t.backlog, int, { better: 'down', caption: 'open at the end of the range' }),
    tileData('Median first response', t.medianFr, hours, { change: 'hours', better: 'down', caption: 'business hours' }),
    tileData('SLA resolution met %', t.resMet, pct, { change: 'pp', caption: 'by creation date' }),
    tileData('CSAT average', t.csat, (v) => fmt.dec(v, 2), { change: 'plain', caption: 'scores 1 to 5' }),
  ]);
  host.draw($('chart-flow'), charts.createdResolved(view.months, c, motion()));
  host.draw($('chart-backlog-months'), charts.backlogMonths(view.months, c, motion()));
  host.draw($('chart-arrivals'), charts.arrivals(view.heatmap, c, motion()));
  const selected = state.cross?.dim === 'category' ? state.cross.value : null;
  host.draw($('chart-categories'), charts.countBars(view.categories, c, { selected, motion: motion() }), (p) => toggleCross({ dim: 'category', value: p.name }));
}

function renderSla(c) {
  const view = model.view(state, 'sla');
  const t = view.tiles;
  tiles($('sla-tiles'), [
    { label: 'SLA first response met %', value: pct(t.frMet), caption: 'met ÷ (met + breached)' },
    { label: 'SLA resolution met %', value: pct(t.resMet), caption: 'met ÷ (met + breached)' },
    { label: 'Breaches', value: int(t.breaches), caption: 'tickets with a breached target' },
    { label: 'Open breaches now', value: int(t.openBreaches), caption: 'still open at the data cut-off' },
    { label: 'Median resolution', value: hours(t.medianRes), caption: 'business hours' },
  ]);
  const priority = state.cross?.dim === 'priority' ? state.cross.value : null;
  host.draw($('chart-priorities'), charts.priorityBars(view.priorities, c, { selected: priority, motion: motion() }), (p) => toggleCross({ dim: 'priority', value: p.name }));
  const cellSel = state.cross?.dim === 'cell' ? state.cross : null;
  const teams = [...new Set(view.matrix.map((r) => r[0]))];
  const priorities = [...new Set(view.matrix.map((r) => r[1]))];
  host.draw($('chart-matrix'), charts.slaMatrix(view.matrix, c, { selected: cellSel, motion: motion() }), (p) => toggleCross({ dim: 'cell', team: teams[p.value[1]], priority: priorities[p.value[0]] }));
  host.draw($('chart-sla-months'), charts.pctMonths(view.months, ['First response', 'Resolution'], c, motion()));
  const rows = model.rows(state).map(ticketOf).filter((r) => r.frOutcome === 'Breached' || r.resOutcome === 'Breached');
  $('breach-count').textContent = `${int(rows.length)} tickets · newest first · 25 per page`;
  table('breaches', $('table-breaches'), {
    caption: 'Tickets with a breached first-response or resolution target',
    pageSize: PAGE,
    emptyText: 'No breach in this selection',
    columns: [
      col('id', 'Ticket', ticketButton),
      col('created', 'Created'),
      col('priority', 'Priority'),
      col('team', 'Team'),
      col('agent', 'Agent'),
      col('frOutcome', 'FR SLA'),
      col('resOutcome', 'Res SLA'),
      num('resHours', 'Resolution', hours),
      col('status', 'Status'),
    ],
    rows,
  }, 'id');
}

function renderTeams(c) {
  const view = model.view(state, 'teams');
  const t = view.tiles;
  tiles($('teams-tiles'), [
    { label: 'Resolved', value: int(t.resolved), caption: 'final resolutions' },
    { label: 'Active agents', value: int(t.activeAgents), caption: 'with a resolution' },
    { label: 'Tickets per agent', value: fmt.dec(t.perAgent, 1), caption: 'resolved ÷ active agents' },
    { label: 'Reopen rate', value: pct(t.reopenRate), caption: 'of tickets ever resolved' },
    { label: 'CSAT average', value: fmt.dec(t.csat, 2), caption: 'scores 1 to 5' },
    { label: 'CSAT response rate', value: pct(t.csatRate), caption: 'of resolved tickets' },
  ]);
  $('ranked-title').textContent = `Agents ranked by ${state.rankBy}`;
  const agent = state.cross?.dim === 'agent' ? state.cross.value : null;
  const ranked = view.ranking.map(([id, value]) => [model.agentName(id), value, id]);
  host.draw($('chart-agents'), charts.agentBars(ranked, state.rankBy, c, { selected: agent, motion: motion() }), (p) => toggleCross({ dim: 'agent', value: p.data.id }));
  const rows = view.scorecard.map(([id, rank, resolved, medianRes, resMet, frMet, reopen, csat, responses]) => ({
    agent: model.agentName(id), rank, resolved, medianRes, resMet, frMet, reopen, csat, responses,
  }));
  barMax.agents = Math.max(0, ...rows.map((r) => r.resolved ?? 0));
  table('agents', $('table-agents'), {
    caption: 'Agent scorecard',
    emptyText: 'No agent in this selection',
    columns: [
      col('agent', 'Agent'),
      num('rank', 'Rank', int),
      num('resolved', 'Resolved', dataBar('agents', int)),
      num('medianRes', 'Median res.', hours),
      num('resMet', 'Res SLA', pct),
      num('frMet', 'FR SLA', pct),
      num('reopen', 'Reopen', pct),
      num('csat', 'CSAT', (v) => fmt.dec(v, 2)),
      num('responses', 'Responses', int),
    ],
    rows,
  }, 'resolved');
  const teams = model.data.dims.teams.filter((name) => !state.team || name === state.team);
  host.draw($('chart-per-agent'), charts.perAgent(view.perAgent, teams, c, motion(), model.data.dims.teams));
  host.draw($('chart-csat'), charts.csatScores(view.csat, c, motion()));
}

function renderBacklog(c) {
  const view = model.view(state, 'backlog');
  const t = view.tiles;
  const snapshot = document.createElement('b');
  snapshot.textContent = fmt.date(view.snapshot);
  $('snapshot').replaceChildren('Snapshot ', snapshot, ' (the end of the month range) · tickets created before the range start count');
  tiles($('backlog-tiles'), [
    { label: 'Backlog', value: int(t.backlog), caption: 'open at the snapshot' },
    { label: 'Backlog change 30 d', value: fmt.signed(t.change30), caption: 'against 30 days earlier' },
    { label: 'Open over 7 days', value: int(t.over7), caption: 'calendar days since creation' },
    { label: 'Oldest open ticket', value: t.oldest === null ? int(null) : `${int(t.oldest)} d`, caption: 'calendar days' },
  ]);
  const lo = monthStart(state.from);
  host.draw($('chart-backlog-days'), charts.backlogDays(view.days.map((v, k) => [dayLabel(lo + k), v]), c, motion()));
  const bucket = state.cross?.dim === 'bucket' ? state.cross.value : null;
  host.draw($('chart-buckets'), charts.countBars(view.buckets, c, { name: 'Open tickets', selected: bucket, motion: motion() }), (p) => toggleCross({ dim: 'bucket', value: p.name }));
  host.draw($('chart-statuses'), charts.countBars(view.statuses, c, { name: 'Open tickets', motion: motion() }));
  const names = model.data.dims.buckets.map((b) => b[0]);
  const teamRows = view.teams.map(([team, counts]) => ({ team, ...Object.fromEntries(counts.map((v, k) => [`b${k}`, v])), total: counts.reduce((s, v) => s + v, 0) }));
  table('teamBuckets', $('table-team-buckets'), {
    caption: 'Open tickets by team and age bucket',
    columns: [col('team', 'Team'), ...names.map((name, k) => num(`b${k}`, name, int)), num('total', 'Total', int)],
    rows: teamRows,
  }, 'total');
  const oldest = view.oldest.map(([id, age]) => ({ ...ticketOf(id - model.data.meta.firstId), age }));
  table('oldest', $('table-oldest'), {
    caption: 'The 25 oldest open tickets at the snapshot',
    emptyText: 'No open ticket at the snapshot',
    columns: [
      col('id', 'Ticket', ticketButton),
      num('age', 'Age (d)', int),
      col('priority', 'Priority'),
      col('team', 'Team'),
      col('status', 'Status'),
    ],
    rows: oldest,
  }, 'age');
}

const RENDER = { overview: renderOverview, sla: renderSla, teams: renderTeams, backlog: renderBacklog };

function render() {
  syncFilters();
  RENDER[state.tab](colours());
  renderTickets();
}

// ---------------------------------------------------------------- start

async function start() {
  mountBanner({ repoUrl: REPO });
  mountThemeToggle($('theme-toggle'));
  const app = $('app');
  try {
    if (!globalThis.echarts) throw new Error('the chart library did not load');
    const response = await fetch('assets/data/replica.json');
    if (!response.ok) throw new Error(`replica.json answered ${response.status}`);
    model = createModel(await response.json());
  } catch (error) {
    $('loading').className = 'app-error';
    $('loading').textContent = `The data could not be loaded (${error.message}). Reload the page to try again.`;
    app.dataset.state = 'error';
    return;
  }
  $('loading').remove();
  $('tickets').hidden = false;
  $('data-until').textContent = `Data as of ${fmt.dateTime(model.data.meta.asOf)}`;
  const themes = registerThemes(globalThis.echarts);
  theme = globalThis.pfTheme?.get() ?? 'dark';
  host = charts.createChartHost(globalThis.echarts, themes, theme);
  document.addEventListener('pf:theme', (e) => {
    theme = e.detail.theme;
    host.setMode(theme);
    render();
  });
  state = { ...normaliseState(store.load(), model.data), cross: null };
  state.tab = tabFromHash() ?? state.tab;
  buildFilters();
  bus.subscribe(() => {
    state.cross = bus.get('cross');
    render();
  });
  $('ticket-search').addEventListener('input', renderTickets);
  document.addEventListener('click', (e) => {
    const button = e.target.closest?.('.tno');
    if (button) showDetail(Number(button.dataset.index));
  });
  $('about-open').addEventListener('click', () => $('about').showModal());
  const tabs = initTabs($('tabs'), {
    onChange: (id) => {
      const tab = id.replace('tab-', '');
      if (tab === state.tab) return;
      history.replaceState(null, '', `#${tab}`);
      state.tab = tab;
      save();
      if (bus.get('cross')) bus.clear();
      else render();
    },
  });
  window.addEventListener('hashchange', () => {
    const tab = tabFromHash();
    if (tab && tab !== state.tab) tabs.select(`tab-${tab}`);
  });
  tabs.select(`tab-${state.tab}`);
  if (!location.hash) history.replaceState(null, '', `#${state.tab}`);
  render();
  app.dataset.state = 'ready';
}

start();
