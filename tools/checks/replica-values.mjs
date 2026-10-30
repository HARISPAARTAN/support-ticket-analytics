// The default KPI tiles of the replica against the `reference` block of web/assets/data/replica.json, which
// tools/build_replica_data.py writes with tools/reference.py (spec section 10). model.js recomputes every tile of
// the four tabs from the shipped ticket arrays; counts must be equal, ratios and hours equal to 1e-9 (relative).
// Usage (from the repository root, Node 22): node tools/checks/replica-values.mjs
import fs from 'node:fs';
import { TABS, createModel, defaultState } from '../../web/assets/js/model.js';

const data = JSON.parse(fs.readFileSync('web/assets/data/replica.json', 'utf8'));
const model = createModel(data);
const state = defaultState();
const problems = [];
let compared = 0;

function same(actual, wanted) {
  if (wanted === null || actual === null) return actual === wanted;
  return Math.abs(actual - wanted) <= 1e-9 * Math.max(1, Math.abs(wanted));
}

function compare(path, actual, wanted) {
  if (wanted !== null && typeof wanted === 'object') {
    for (const key of Object.keys(wanted)) compare(`${path}.${key}`, actual?.[key] ?? null, wanted[key]);
    return;
  }
  compared += 1;
  if (!same(actual, wanted)) problems.push(`${path}: replica ${actual}, reference ${wanted}`);
}

for (const tab of TABS) {
  const wanted = data.reference[tab]?.tiles;
  if (!wanted) {
    problems.push(`${tab}: the reference block has no tiles`);
    continue;
  }
  compare(tab, model.view({ ...state, tab }, tab).tiles, wanted);
}
for (const problem of problems) console.log(`FAIL ${problem}`);
console.log(`replica-values: ${compared} tile values of ${TABS.length} tabs compared, ${problems.length} differ`);
process.exit(problems.length ? 1 : 0);
