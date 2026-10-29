// The chart options of web/assets/js/charts.js: series colours of the spec, axes, the selection dimming, unlabelled
// heatmap cells and the kit's number formats (never Intl compact notation).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as charts from '../../web/assets/js/charts.js';
import { createModel, defaultState } from '../../web/assets/js/model.js';

const root = new URL('../../', import.meta.url);
const model = createModel(JSON.parse(readFileSync(new URL('web/assets/data/replica.json', root), 'utf8')));
const C = {
  text: '#E6EDF3', muted: '#93A1B0', border: '#1F2A36', surface: '#121820', surface2: '#182130', accent: '#F2A93B',
  ok: '#3DDC97', warn: '#FACC15', danger: '#F87171',
  chart: ['#C38102', '#058DB5', '#02AB70', '#AB6FE5', '#CA445C', '#77A304', '#028E7F', '#7A84EF'],
  seq: ['#6D4200', '#8B5502', '#AB6901', '#CB7E04', '#EC940D', '#FFB257'],
};
const state = defaultState();

test('hours and month labels', () => {
  assert.equal(charts.hoursText(3.4333), '3.43 h');
  assert.equal(charts.hoursText(0.75), '45 min');
  assert.equal(charts.hoursText(null), '–');
  assert.deepEqual(charts.monthLabels(['2025-01', '2025-02']), ['Jan', 'Feb']);
  assert.deepEqual(charts.monthLabels(['2024-12', '2025-01']), ['Dec 2024', 'Jan 2025']);
  assert.equal(charts.rankText('SLA resolution met %')(0.88642).replace(/\s/, ' '), '88.6 %'); // fmt.pct: no-break space
  assert.equal(charts.rankText('CSAT average')(3.977), '3.98');
  assert.equal(charts.rankText('Resolved')(1234), '1,234');
});

test('overview: created in chart-1, resolved in chart-2, the backlog line in the accent', () => {
  const view = model.view(state, 'overview');
  const bars = charts.createdResolved(view.months, C);
  assert.deepEqual(bars.series.map((s) => [s.name, s.itemStyle.color]), [['Created', C.chart[0]], ['Resolved', C.chart[1]]]);
  assert.equal(bars.xAxis.data.length, 21);
  assert.equal(bars.xAxis.data[0], 'Jan 2024');
  assert.equal(bars.series[0].data.reduce((s, v) => s + v, 0), view.tiles.created.value);
  const line = charts.backlogMonths(view.months, C);
  assert.equal(line.series[0].lineStyle.color, C.accent);
  assert.equal(line.series[0].data.at(-1), view.tiles.backlog.value);
});

test('category bars dim the others while one is selected', () => {
  const view = model.view(state, 'overview');
  const option = charts.countBars(view.categories, C, { selected: 'Billing' });
  const opacity = option.series[0].data.map((d) => d.itemStyle.opacity);
  assert.deepEqual(opacity, view.categories.map(([name]) => (name === 'Billing' ? 1 : 0.35)));
  assert.equal(option.series[0].label.formatter({ value: 12345 }), '12,345');
});

test('arrivals: 7 x 24 cells without labels on the sequential ramp', () => {
  const view = model.view(state, 'overview');
  const option = charts.arrivals(view.heatmap, C);
  assert.equal(option.series[0].data.length, 168);
  assert.equal(option.series[0].label, undefined);
  assert.deepEqual(option.visualMap.inRange.color, C.seq);
  assert.equal(option.visualMap.max, Math.max(...view.heatmap));
  assert.equal(option.visualMap.min, 1); // a cell without tickets is out of range ...
  assert.equal(option.visualMap.outOfRange.color, C.surface2); // ... and takes surface-2, never a step of the ramp
  assert.deepEqual(option.yAxis.data, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
});

test('SLA: priority bars on a 0 to 100 % axis, the matrix from danger to surface-2', () => {
  const view = model.view(state, 'sla');
  const bars = charts.priorityBars(view.priorities, C, { selected: 'P1' });
  assert.deepEqual([bars.yAxis.min, bars.yAxis.max], [0, 1]);
  assert.deepEqual(bars.series[0].data.map((d) => d.itemStyle.opacity), [1, 0.35, 0.35, 0.35]);
  const matrix = charts.slaMatrix(view.matrix, C, { selected: { team: 'Integrations', priority: 'P1' } });
  assert.equal(matrix.series[0].data.length, 16);
  assert.deepEqual(matrix.visualMap.inRange.color, [C.danger, C.warn, C.surface2]);
  assert.deepEqual([matrix.visualMap.min, matrix.visualMap.max], [0.75, 0.95]);
  assert.equal(matrix.series[0].data.filter((d) => d.itemStyle.opacity === 1).length, 1);
  assert.equal(matrix.series[0].label, undefined);
  const lines = charts.pctMonths(view.months, ['First response', 'Resolution'], C);
  assert.deepEqual(lines.series.map((s) => s.lineStyle.color), [C.chart[0], C.chart[1]]);
  assert.equal(lines.xAxis.boundaryGap, true); // the last month label keeps room at the right edge
});

test('teams: ranked bars use the scale of the measure, one line per team, CSAT in status colours', () => {
  const view = model.view({ ...state, rankBy: 'SLA resolution met %' }, 'teams');
  const rows = view.ranking.map(([id, value]) => [model.agentName(id), value, id]);
  const option = charts.agentBars(rows, 'SLA resolution met %', C, { selected: rows[0][2] });
  assert.deepEqual([option.xAxis.min, option.xAxis.max], [0, 1]);
  assert.equal(option.series[0].data.filter((d) => d.itemStyle.opacity === 1).length, 1);
  const csat = charts.agentBars(rows, 'CSAT average', C);
  assert.deepEqual([csat.xAxis.min, csat.xAxis.max], [1, 5]);
  const teams = model.data.dims.teams;
  const per = charts.perAgent(view.perAgent, teams, C);
  assert.deepEqual(per.series.map((s) => s.lineStyle.color), C.chart.slice(0, 4));
  const scores = charts.csatScores(view.csat, C);
  assert.deepEqual(scores.series[0].data.map((d) => d.itemStyle.color), [C.danger, C.danger, C.warn, C.ok, C.ok]);
});

test('teams: a line keeps the colour of its team under a team filter', () => {
  const teams = model.data.dims.teams;
  const months = [['2025-09', [2.5]]];
  const billing = charts.perAgent(months, ['Billing & Accounts'], C, true, teams);
  assert.equal(billing.series[0].lineStyle.color, C.chart[teams.indexOf('Billing & Accounts')]);
  assert.equal(billing.series[0].itemStyle.color, C.chart[teams.indexOf('Billing & Accounts')]);
  assert.deepEqual(billing.series[0].data, [2.5]);
  const first = charts.perAgent(months, [teams[0]], C);
  assert.equal(first.series[0].lineStyle.color, C.chart[0]);
});

test('backlog: one point per day, dates on the axis', () => {
  const days = [['2025-09-29', 141], ['2025-09-30', 140]];
  const option = charts.backlogDays(days, C);
  assert.deepEqual(option.series[0].data, [141, 140]);
  assert.equal(option.xAxis.axisLabel.formatter('2025-09-30'), '30 Sep 2025');
});

test('no option uses Intl compact notation', () => {
  const text = readFileSync(new URL('web/assets/js/charts.js', root), 'utf8');
  assert.ok(!text.includes("notation: 'compact'"));
  assert.ok(!text.includes('toLocaleString'));
});
