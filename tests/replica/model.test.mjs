// web/assets/js/model.js on web/assets/data/replica.json must reproduce tests/replica/expected.json, which
// tools/build_replica_data.py computes with tools/reference.py from the CSV files.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  createModel, defaultState, normaliseState, summary, sub, div, median, monthsBetween, shiftYear, dayNumber, dayLabel, TABS,
} from '../../web/assets/js/model.js';

const root = new URL('../../', import.meta.url);
const data = JSON.parse(readFileSync(new URL('web/assets/data/replica.json', root), 'utf8'));
const expected = JSON.parse(readFileSync(new URL('tests/replica/expected.json', root), 'utf8'));
const model = createModel(data);

// Compare the keys the reference wrote; numbers to a relative 1e-9 (the reference divides in float64 too).
function close(actual, wanted, path) {
  if (wanted === null || typeof wanted !== 'object') {
    if (typeof wanted === 'number' && typeof actual === 'number') {
      const scale = Math.max(1, Math.abs(wanted));
      assert.ok(Math.abs(actual - wanted) <= 1e-9 * scale, `${path}: ${actual} != ${wanted}`);
    } else {
      assert.equal(actual, wanted, path);
    }
    return;
  }
  assert.ok(actual !== null && typeof actual === 'object', `${path}: expected an object or array, got ${actual}`);
  if (Array.isArray(wanted)) {
    assert.ok(Array.isArray(actual), `${path}: expected an array`);
    assert.equal(actual.length, wanted.length, `${path}: length`);
  }
  for (const key of Object.keys(wanted)) close(actual[key], wanted[key], `${path}.${key}`);
}

test('the expected file holds the 17 states, the default first', () => {
  assert.equal(expected.states.length, 17);
  assert.deepEqual(expected.states[0].state, defaultState());
});

for (const entry of expected.states) {
  test(`state "${entry.name}": every tab matches the reference`, () => {
    for (const tab of TABS) close(model.view(entry.state, tab), entry.views[tab], `${entry.name}.${tab}`);
  });
}

test('the reference block equals the default views', () => {
  for (const tab of TABS) close(model.view(defaultState(), tab), data.reference[tab], `reference.${tab}`);
});

test('days and months', () => {
  assert.equal(dayNumber(2024, 1, 1), 0);
  assert.equal(dayLabel(dayNumber(2025, 9, 30)), '2025-09-30');
  assert.equal(model.lastDay, 638);
  assert.deepEqual(monthsBetween('2024-11', '2025-02'), ['2024-11', '2024-12', '2025-01', '2025-02']);
  assert.equal(dayLabel(shiftYear(dayNumber(2025, 2, 28), -1)), '2024-02-29');
  assert.equal(dayLabel(shiftYear(dayNumber(2025, 3, 15), -1)), '2024-03-15');
  assert.equal(dayLabel(shiftYear(dayNumber(2024, 2, 29), 1)), '2025-02-28');
});

test('blank arithmetic follows DAX', () => {
  assert.equal(sub(null, null), null);
  assert.equal(sub(null, 5), -5);
  assert.equal(div(1, 0), null);
  assert.equal(div(0, 4), null);
  assert.equal(div(null, 2), null);
  assert.equal(div(1, 4), 0.25);
  assert.equal(median([]), null);
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2]), 2.5);
});

test('a stored state is cleaned before use', () => {
  const raw = {
    tab: 'nowhere',
    from: '2025-06',
    to: '2024-02',
    team: 'Integrations',
    priorities: ['P4', 'P9', 'P1'],
    channel: 'Fax',
    cross: { dim: 'cell', team: 'Integrations', priority: 'P1', extra: 1 },
    rankBy: 'Height',
  };
  assert.deepEqual(normaliseState(raw, data), {
    ...defaultState(),
    from: '2024-02',
    to: '2025-06',
    team: 'Integrations',
    priorities: ['P1', 'P4'],
    cross: { dim: 'cell', team: 'Integrations', priority: 'P1' },
  });
  assert.deepEqual(normaliseState('not an object', data), defaultState());
  assert.equal(normaliseState({ cross: { dim: 'bucket', value: '9 d' } }, data).cross, null);
  assert.equal(normaliseState({ from: '2023-12' }, data).from, '2024-01');
});

test('the phone filter summary', () => {
  assert.equal(summary(defaultState()), 'Jan 2024 – Sep 2025 · all teams · all priorities · all channels');
  assert.equal(
    summary({ ...defaultState(), from: '2025-03', to: '2025-03', team: 'Integrations', priorities: ['P1', 'P2'], channel: 'Chat' }),
    'Mar 2025 · Integrations · P1, P2 · Chat',
  );
});

test('the ticket table: rows, search, sort and detail', () => {
  const state = defaultState();
  const rows = model.rows(state, 'overview');
  assert.equal(rows.length, expected.states[0].views.overview.table.count);
  const first = model.ticket(0);
  assert.equal(first.number, 'QS-100001');
  assert.match(first.created, /^2024-01-01 \d\d:\d\d$/);
  assert.match(first.customer, /^Account C\d{4}$/);
  assert.deepEqual(model.search(rows, 'qs-100001'), [0]);
  const hits = model.search(rows, first.subject.slice(0, 12).toUpperCase());
  assert.ok(hits.includes(0) && hits.every((i) => model.ticket(i).subject.toLowerCase().includes(first.subject.slice(0, 12).toLowerCase())));
  const byPriority = model.sortRows(rows, 'priority', 'asc');
  assert.equal(model.ticket(byPriority[0]).priority, 'P1');
  assert.deepEqual(model.sortRows(rows).slice(0, 25).map((i) => model.ticket(i).id), expected.states[0].views.overview.table.ids);
  const backlog = model.rows(state, 'backlog');
  assert.equal(backlog.length, expected.states[0].views.backlog.tiles.backlog);
});
