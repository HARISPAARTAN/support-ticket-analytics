// Screenshots and browser checks of the replica (umbrella section 12): every tab at 1440 x 900 and 390 x 844, in the
// dark and the light theme, plus the interactions of docs/screenshots/SHOTLIST.md. A built-in static server serves
// web/ on 127.0.0.1; the run fails on any request that leaves that server, on a console error or page error, on
// horizontal scrolling of the page, when a table scrolls sideways inside its card at 1440 px, when a tab button lies
// outside the viewport at 390 px, when the banner is not at the top before a full-page capture, and when a focused
// control ends up under the sticky filter bar. With
// URL=<address of the published page> it checks that page instead of the local copy (requests must then stay on it).
// Usage (from the repository root, Node 22; Playwright is not a dependency of this repository):
//   PLAYWRIGHT_FROM=<package.json of a folder that has playwright installed> OUT=<folder outside the repository> \
//     node tools/checks/shots.mjs
// It also writes thumb-1440.jpg (the Overview at 1440 x 900, dark) for the portfolio hub; THUMB_QUALITY sets the
// JPEG quality (default 80). Chrome comes from the local installation (channel "chrome"); nothing is downloaded.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const ROOT = path.resolve('web');
const REPO = path.resolve('.');
const FROM = process.env.PLAYWRIGHT_FROM;
const OUT = process.env.OUT ? path.resolve(process.env.OUT) : null;
if (!FROM || !OUT) {
  console.error('shots: set PLAYWRIGHT_FROM (a package.json path) and OUT (a folder outside the repository)');
  process.exit(2);
}
if (OUT === REPO || OUT.startsWith(REPO + path.sep)) {
  console.error('shots: OUT must lie outside the repository');
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });
const { chromium } = createRequire(FROM)('playwright');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};
const server = http.createServer((req, res) => {
  const route = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = path.join(ROOT, route.endsWith('/') ? `${route}index.html` : route);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404);
    res.end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
const LIVE = process.env.URL ? process.env.URL.replace(/\/+$/, '') : null;
if (!LIVE) await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const BASE = LIVE ?? `http://127.0.0.1:${server.address().port}`;

const TABS = ['overview', 'sla', 'teams', 'backlog'];
const SIZES = [[1440, 900], [390, 844]];
const KEY = 'pf.support-ticket-analytics.v1';
const problems = [];
let shots = 0;

async function open(browser, theme, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await context.addInitScript((mode) => {
    try {
      localStorage.setItem('hh-theme', mode);
    } catch {
      /* storage blocked: the theme falls back to the system preference */
    }
  }, theme);
  const page = await context.newPage();
  const where = `${theme} ${width}`;
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`${where}: console error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`${where}: page error: ${err.message}`));
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith(BASE) && !url.startsWith('data:') && !url.startsWith('blob:')) problems.push(`${where}: external request ${url}`);
  });
  return { context, page, where };
}

async function load(page, tab) {
  await page.goto(`${BASE}/index.html?view=${tab}#${tab}`);
  await page.waitForSelector('#app[data-state="ready"]', { timeout: 20000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(250);
}

async function shot(page, where, name, options = {}) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) problems.push(`${where}: ${name} scrolls sideways by ${overflow} px`);
  // A full-page capture is taken from the top: after a scroll the fixed banner and the sticky filter bar would be drawn mid-page.
  if (options.fullPage !== false) {
    await page.evaluate(() => window.scrollTo(0, 0));
    const scrolled = await page.evaluate(() => window.scrollY);
    if (scrolled > 0.5) problems.push(`${where}: ${name}: the page is scrolled by ${scrolled} px before the capture, not at the top`);
  }
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true, ...options });
  shots += 1;
}

// At 1440 px every table of the open tab, the ticket table first, must fit its card: no scrolling inside the wrapper.
async function tablesFit(page, where, tab) {
  const wrappers = await page.evaluate(() => [...document.querySelectorAll('.pf-table-wrap')]
    .filter((w) => w.offsetParent !== null)
    .map((w) => ({ label: w.getAttribute('aria-label'), id: w.parentElement.id, scroll: w.scrollWidth, client: w.clientWidth })));
  if (!wrappers.some((w) => w.id === 'table-tickets')) problems.push(`${where}: ${tab}: the ticket table is missing`);
  for (const w of wrappers) {
    if (w.scroll > w.client + 1) problems.push(`${where}: ${tab}: the table "${w.label}" scrolls inside its card (${w.scroll} > ${w.client} px)`);
  }
}

// At 390 px the four tab buttons must all lie inside the viewport.
async function tabsInside(page, where, tab) {
  const outside = await page.evaluate((ids) => ids.filter((id) => {
    const box = document.getElementById(`tab-${id}`).getBoundingClientRect();
    return box.left < 0 || box.top < 0 || box.right > window.innerWidth || box.bottom > window.innerHeight;
  }), TABS);
  for (const id of outside) problems.push(`${where}: ${tab}: the tab button ${id} lies outside the viewport`);
}

// A control that receives keyboard focus must not sit under the sticky filter bar (scroll-padding-top in app.css).
async function focusVisible(page, where, selector) {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.focus(selector);
  await page.waitForTimeout(100);
  const gap = await page.evaluate((sel) => {
    const bar = document.getElementById('filters').getBoundingClientRect();
    const box = document.querySelector(sel).getBoundingClientRect();
    return box.top - bar.bottom;
  }, selector);
  if (gap < 0) problems.push(`${where}: ${selector} is ${-gap} px under the filter bar after focus`);
}

// Clicks the bar of `category` in the bar chart inside `#id` (ECharts draws SVG, so the point is computed).
async function clickBar(page, id, category) {
  const point = await page.evaluate(([chartId, name]) => {
    const el = document.getElementById(chartId);
    el.scrollIntoView({ block: 'center' });
    const chart = globalThis.echarts.getInstanceByDom(el);
    const index = chart.getOption().yAxis[0].data.indexOf(name);
    const value = chart.getOption().series[0].data[index].value;
    const [x, y] = chart.convertToPixel({ gridIndex: 0 }, [value / 2, name]);
    const box = el.getBoundingClientRect();
    return [box.left + x, box.top + y];
  }, [id, category]);
  await page.mouse.click(point[0], point[1]);
  await page.waitForTimeout(250);
}

const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  for (const theme of ['dark', 'light']) {
    for (const size of SIZES) {
      const { context, page, where } = await open(browser, theme, size);
      for (const tab of TABS) {
        await load(page, tab);
        if (size[0] === 1440) await tablesFit(page, where, tab);
        if (size[0] === 390) await tabsInside(page, where, tab);
        await shot(page, where, `${theme}-${size[0]}-${tab}`);
      }
      await load(page, 'overview');
      await focusVisible(page, where, '#ticket-search');
      await context.close();
    }
  }
  // interactions, dark, 1440 px
  const { context, page, where } = await open(browser, 'dark', SIZES[0]);
  try {
    await load(page, 'overview');
    await shot(page, where, '09-replica', { fullPage: false });
    // the hub thumbnail: 1440 x 900, JPEG (THUMB_QUALITY, default 80)
    await page.screenshot({ path: path.join(OUT, 'thumb-1440.jpg'), type: 'jpeg', quality: Number(process.env.THUMB_QUALITY ?? 80) });
    // a rise of the backlog is bad news: danger colour, and the arrow still points up
    const backlogDelta = await page.textContent('#overview-tiles > :nth-child(3) .pf-kpi__delta');
    if (!backlogDelta.startsWith('▲') || !backlogDelta.includes('+17.6')) problems.push(`${where}: the backlog change reads ${backlogDelta}`);
    const before = await page.textContent('#overview-tiles .pf-kpi__value');
    await clickBar(page, 'chart-categories', 'Billing');
    const chip = await page.textContent('#cross-chip');
    const after = await page.textContent('#overview-tiles .pf-kpi__value');
    if (!chip.includes('Billing') || before === after) problems.push(`${where}: the category cross-filter did not apply`);
    await shot(page, where, 'dark-1440-overview-cross-filter');
    await page.click('#tab-sla');
    if ((await page.textContent('#cross-chip')).includes('Billing')) problems.push(`${where}: the cross-filter survived the tab change`);
    await page.click('#priority-chips [data-priority="P1"]');
    await page.waitForTimeout(250);
    await shot(page, where, 'dark-1440-sla-p1');
    await page.click('#tab-teams');
    await page.selectOption('#rank-by', 'CSAT average');
    await page.waitForTimeout(250);
    if (!(await page.textContent('#ranked-title')).includes('CSAT average')) problems.push(`${where}: Rank by did not switch`);
    await shot(page, where, 'dark-1440-teams-rank-csat');
    await page.click('#tab-backlog');
    await page.click('#table-oldest .tno');
    await page.waitForSelector('#detail[open]');
    await shot(page, where, 'dark-1440-ticket-detail', { fullPage: false });
    await page.keyboard.press('Escape');
    await page.fill('#ticket-search', 'zzzz-no-such-ticket');
    if (!(await page.textContent('#table-tickets')).includes('No ticket matches the search')) {
      problems.push(`${where}: the ticket search did not filter`);
    }
    await page.click('#about-open');
    await page.waitForSelector('#about[open]');
    await shot(page, where, 'dark-1440-about', { fullPage: false });
    await page.keyboard.press('Escape');
    if (!(await page.evaluate((key) => localStorage.getItem(key), KEY))) problems.push(`${where}: the view was not stored`);
    await page.click('#reset');
    if (await page.evaluate((key) => localStorage.getItem(key), KEY)) problems.push(`${where}: Reset did not clear ${KEY}`);
    if ((await page.getAttribute('#priority-chips [data-priority="P1"]', 'aria-pressed')) !== 'false') {
      problems.push(`${where}: Reset did not clear the priorities`);
    }
  } catch (error) {
    problems.push(`${where}: interaction failed: ${error.message.split('\n')[0]}`);
  }
  await context.close();
  // phone: the stacked ticket cards and the filter disclosure
  const phone = await open(browser, 'dark', SIZES[1]);
  try {
    await load(phone.page, 'sla');
    await phone.page.click('#filters-toggle');
    await shot(phone.page, phone.where, 'dark-390-filters-open', { fullPage: false });
    await phone.page.click('#filters-toggle');
    await phone.page.locator('#table-breaches').scrollIntoViewIfNeeded();
    await shot(phone.page, phone.where, 'dark-390-breach-cards', { fullPage: false });
  } catch (error) {
    problems.push(`${phone.where}: interaction failed: ${error.message.split('\n')[0]}`);
  }
  await phone.context.close();
} finally {
  await browser.close();
  if (!LIVE) server.close();
}

for (const problem of problems) console.log(`FAIL ${problem}`);
console.log(`shots: ${shots} screenshots of ${LIVE ?? 'web/'} in ${OUT}, ${problems.length} problems`);
process.exit(problems.length ? 1 : 0);
