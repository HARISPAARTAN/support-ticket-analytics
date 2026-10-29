// ECharts options of the replica: pure functions from a view of model.js and the colours of the active theme to an
// option object (no DOM access), plus a small host that draws them with the kit's chart themes. Every number goes
// through the kit's fmt helpers. `selected` dims the other bars while a cross-filter of that chart is active.
import { fmt } from '../../kit/kit.js';
import { MONTH_NAMES, WEEKDAYS } from './model.js';

const MONO = '"JetBrains Mono", Consolas, monospace';
const escape = (text) => String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);

// Hours as the report shows them: whole minutes below one hour, otherwise hours with two decimals.
export const hoursText = (h) => {
  if (h === null || h === undefined) return fmt.dec(null);
  return h < 1 ? `${fmt.int(h * 60)} min` : `${fmt.dec(h, 2)} h`;
};

// Month axis labels: "Jan" while every month lies in one year, "Jan 2024" otherwise.
export function monthLabels(months) {
  const years = new Set(months.map((m) => m.slice(0, 4)));
  return months.map((m) => {
    const name = MONTH_NAMES[Number(m.slice(5, 7)) - 1];
    return years.size > 1 ? `${name} ${m.slice(0, 4)}` : name;
  });
}

function base(c, motion) {
  return {
    animation: motion,
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', confine: true },
    textStyle: { fontFamily: 'Inter, system-ui, sans-serif' },
    color: c.chart,
  };
}

function axisTooltip(show) {
  return (params) => {
    const list = Array.isArray(params) ? params : [params];
    const head = escape(list[0]?.axisValueLabel ?? list[0]?.name ?? '');
    return [head, ...list.map((p) => `${p.marker}${escape(p.seriesName)}: <b>${show(p.value)}</b>`)].join('<br>');
  };
}

const valueAxis = (formatter, extra = {}) => ({ type: 'value', axisLabel: { formatter, hideOverlap: true }, ...extra });
const dim = (selected, key) => (selected === null || selected === key ? 1 : 0.35);
const legend = { type: 'scroll', top: 0, right: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10 };
const withLegend = { left: 8, right: 16, top: 32, bottom: 8, containLabel: true };

// Overview: created (chart-1) and resolved (chart-2) per month; rows are [ym, created, resolved, backlog].
export function createdResolved(months, c, motion = true) {
  const bar = (k, colour) => ({ type: 'bar', barMaxWidth: 16, data: months.map((r) => r[k]), itemStyle: { color: colour, borderRadius: [3, 3, 0, 0] } });
  return {
    ...base(c, motion),
    legend,
    grid: withLegend,
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((v) => fmt.int(v)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])) },
    yAxis: valueAxis((v) => fmt.compact(v)),
    series: [{ name: 'Created', ...bar(1, c.chart[0]) }, { name: 'Resolved', ...bar(2, c.chart[1]) }],
  };
}

// Overview: the backlog at each month end (accent).
export function backlogMonths(months, c, motion = true) {
  return {
    ...base(c, motion),
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((v) => fmt.int(v)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])), boundaryGap: false },
    yAxis: valueAxis((v) => fmt.int(v), { scale: true }),
    series: [
      { name: 'Backlog', type: 'line', data: months.map((r) => r[3]), lineStyle: { width: 2.5, color: c.accent }, itemStyle: { color: c.accent }, symbol: 'circle', symbolSize: 5 },
    ],
  };
}

// Horizontal count bars ([name, value]) in chart-1, in the order given; `name` labels the value in the tooltip.
export function countBars(rows, c, { name = 'Created', selected = null, motion = true } = {}) {
  return {
    ...base(c, motion),
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `${escape(p.name)}<br>${escape(name)}: <b>${fmt.int(p.value)}</b>` },
    xAxis: valueAxis((v) => fmt.compact(v)),
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[0]) },
    series: [
      {
        name,
        type: 'bar',
        barMaxWidth: 26,
        cursor: 'pointer',
        data: rows.map((r) => ({ value: r[1], itemStyle: { color: c.chart[0], opacity: dim(selected, r[0]), borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: c.text, fontFamily: MONO, formatter: (p) => fmt.int(p.value) },
      },
    ],
  };
}

// Overview: tickets created per weekday and hour of the day (Lisbon time) on the kit's sequential ramp; the cells
// carry no labels, so no text sits on a coloured cell (the tooltip gives the count). The ramp starts at one ticket;
// a cell without tickets is out of range and takes surface-2, so it never reads as the loudest step of the ramp.
export function arrivals(cells, c, motion = true) {
  const data = cells.map((v, k) => [k % 24, Math.floor(k / 24), v]);
  const hour = (h) => `${String(h).padStart(2, '0')}:00`;
  return {
    ...base(c, motion),
    grid: { left: 8, right: 8, top: 8, bottom: 44, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `${WEEKDAYS[p.value[1]]} ${hour(p.value[0])}<br>Created: <b>${fmt.int(p.value[2])}</b>` },
    xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')) },
    yAxis: { type: 'category', inverse: true, data: WEEKDAYS },
    visualMap: {
      min: 1,
      max: Math.max(1, ...cells),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 120,
      itemWidth: 10,
      inRange: { color: c.seq },
      outOfRange: { color: c.surface2 },
      textStyle: { color: c.muted },
      formatter: (v) => fmt.int(v),
    },
    series: [{ name: 'Created', type: 'heatmap', data, itemStyle: { borderColor: c.surface, borderWidth: 1 } }],
  };
}

// SLA: first response (chart-1) and resolution (chart-2) met % per priority; rows are [priority, fr, res].
export function priorityBars(rows, c, { selected = null, motion = true } = {}) {
  const point = (r, k, colour) => ({ value: r[k], itemStyle: { color: colour, opacity: dim(selected, r[0]), borderRadius: [3, 3, 0, 0] } });
  return {
    ...base(c, motion),
    legend,
    grid: withLegend,
    tooltip: { trigger: 'axis', confine: true, axisPointer: { type: 'shadow' }, formatter: axisTooltip((v) => fmt.pct(v)) },
    xAxis: { type: 'category', data: rows.map((r) => r[0]) },
    yAxis: valueAxis((v) => fmt.pct(v, 0), { min: 0, max: 1 }),
    series: [
      { name: 'First response', type: 'bar', cursor: 'pointer', barMaxWidth: 28, data: rows.map((r) => point(r, 1, c.chart[0])) },
      { name: 'Resolution', type: 'bar', cursor: 'pointer', barMaxWidth: 28, data: rows.map((r) => point(r, 2, c.chart[1])) },
    ],
  };
}

// SLA: resolution met % per team and priority ([team, priority, value]), danger at 75 % and below, warn at 85 %,
// surface-2 from 95 %. As in the arrivals chart the cells carry no labels; the tooltip gives the value.
export function slaMatrix(matrix, c, { selected = null, motion = true } = {}) {
  const teams = [...new Set(matrix.map((r) => r[0]))];
  const priorities = [...new Set(matrix.map((r) => r[1]))];
  const on = (t, p) => selected === null || (selected.team === t && selected.priority === p);
  const data = matrix.map(([t, p, v]) => ({
    value: [priorities.indexOf(p), teams.indexOf(t), v === null ? '-' : v],
    itemStyle: { opacity: on(t, p) ? 1 : 0.35 },
  }));
  const value = (p) => fmt.pct(p.value[2] === '-' ? null : p.value[2]);
  return {
    ...base(c, motion),
    grid: { left: 8, right: 8, top: 8, bottom: 44, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `${escape(teams[p.value[1]])} · ${escape(priorities[p.value[0]])}<br>Resolution SLA met: <b>${value(p)}</b>` },
    xAxis: { type: 'category', data: priorities },
    yAxis: { type: 'category', inverse: true, data: teams },
    visualMap: {
      type: 'continuous',
      min: 0.75,
      max: 0.95,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 120,
      itemWidth: 10,
      inRange: { color: [c.danger, c.warn, c.surface2] },
      textStyle: { color: c.muted },
      formatter: (v) => fmt.pct(v, 0),
    },
    series: [{ name: 'Resolution SLA met', type: 'heatmap', cursor: 'pointer', data, itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 } }],
  };
}

// Month lines of two or more ratios ([ym, a, b, ...]) in chart-1, chart-2, ...
export function pctMonths(months, names, c, motion = true) {
  return {
    ...base(c, motion),
    legend,
    grid: withLegend,
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((v) => fmt.pct(v)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])), boundaryGap: true },
    yAxis: valueAxis((v) => fmt.pct(v, 0), { max: 1, min: (v) => Math.max(0, Math.floor(v.min * 10) / 10) }),
    series: names.map((name, k) => ({
      name,
      type: 'line',
      data: months.map((r) => r[k + 1]),
      lineStyle: { width: 2.5, color: c.chart[k] },
      itemStyle: { color: c.chart[k] },
      symbol: 'circle',
      symbolSize: 5,
    })),
  };
}

// The text of a ranking value: a percentage, a CSAT average with two decimals or a count.
export function rankText(rankBy) {
  if (rankBy.endsWith('%')) return (v) => fmt.pct(v);
  if (rankBy === 'CSAT average') return (v) => fmt.dec(v, 2);
  return (v) => fmt.int(v);
}

// Teams: agents ranked by the chosen measure ([name, value, id]); a click filters the tables to that agent.
export function agentBars(rows, rankBy, c, { selected = null, motion = true } = {}) {
  const show = rankText(rankBy);
  const pct = rankBy.endsWith('%');
  const scale = pct ? { min: 0, max: 1 } : rankBy === 'CSAT average' ? { min: 1, max: 5 } : {};
  return {
    ...base(c, motion),
    grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `${escape(p.name)}<br>${escape(rankBy)}: <b>${show(p.value)}</b>` },
    xAxis: valueAxis(pct ? (v) => fmt.pct(v, 0) : (v) => fmt.compact(v), scale),
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[0]), axisLabel: { width: 140, overflow: 'truncate' } },
    series: [
      {
        name: rankBy,
        type: 'bar',
        cursor: 'pointer',
        barMaxWidth: 18,
        data: rows.map((r) => ({ value: r[1], id: r[2], itemStyle: { color: c.chart[0], opacity: dim(selected, r[2]), borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: c.text, fontFamily: MONO, formatter: (p) => show(p.value) },
      },
    ],
  };
}

// Teams: tickets per agent per month, one line per team ([ym, [value per team]]); allTeams (the full team list) fixes the
// colour per team, so a line keeps its colour under a team filter.
export function perAgent(months, teams, c, motion = true, allTeams = teams) {
  return {
    ...base(c, motion),
    legend,
    grid: withLegend,
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((v) => fmt.dec(v, 1)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])), boundaryGap: false },
    yAxis: valueAxis((v) => fmt.int(v)),
    series: teams.map((name, k) => {
      const idx = allTeams.indexOf(name);
      const colour = c.chart[idx < 0 ? k : idx];
      return {
        name,
        type: 'line',
        data: months.map((r) => r[1][k]),
        lineStyle: { width: 2, color: colour },
        itemStyle: { color: colour },
        symbol: 'none',
      };
    }),
  };
}

// Teams: CSAT responses per score 1 to 5 in danger (1 and 2), warn (3) and ok (4 and 5).
export function csatScores(scores, c, motion = true) {
  const colour = (k) => (k < 2 ? c.danger : k === 2 ? c.warn : c.ok);
  return {
    ...base(c, motion),
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `Score ${p.name}<br>Responses: <b>${fmt.int(p.value)}</b>` },
    xAxis: { type: 'category', data: ['1', '2', '3', '4', '5'] },
    yAxis: valueAxis((v) => fmt.compact(v)),
    series: [{ name: 'Responses', type: 'bar', barMaxWidth: 40, data: scores.map((v, k) => ({ value: v, itemStyle: { color: colour(k), borderRadius: [4, 4, 0, 0] } })) }],
  };
}

// Backlog: open tickets at the end of every day of the range ([iso date, value]).
export function backlogDays(days, c, motion = true) {
  return {
    ...base(c, motion),
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((v) => fmt.int(v)) },
    xAxis: { type: 'category', data: days.map((d) => d[0]), boundaryGap: false, axisLabel: { formatter: (v) => fmt.date(v), hideOverlap: true } },
    yAxis: valueAxis((v) => fmt.int(v), { scale: true }),
    series: [
      {
        name: 'Backlog',
        type: 'line',
        data: days.map((d) => d[1]),
        showSymbol: false,
        lineStyle: { width: 2, color: c.accent },
        itemStyle: { color: c.accent },
        areaStyle: { color: c.accent, opacity: 0.12 },
      },
    ],
  };
}

// Draws options into elements with the kit's themes; charts are created on first use, re-created after a theme
// switch and resized with their element.
export function createChartHost(echarts, themes, mode) {
  const charts = new Map();
  let current = mode;
  const observer = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => entries.forEach((e) => charts.get(e.target)?.resize()))
    : null;
  return {
    draw(el, option, onClick) {
      let chart = charts.get(el);
      if (!chart) {
        chart = echarts.init(el, themes[current], { renderer: 'svg' });
        charts.set(el, chart);
        observer?.observe(el);
      }
      chart.setOption(option, { notMerge: true });
      chart.off('click');
      if (onClick) chart.on('click', onClick);
      chart.resize();
      return chart;
    },
    setMode(next) {
      if (next === current) return;
      current = next;
      for (const [el, chart] of charts) {
        observer?.unobserve(el);
        chart.dispose();
      }
      charts.clear();
    },
  };
}
