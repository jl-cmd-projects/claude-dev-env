const { test } = require('node:test');
const assert = require('node:assert/strict');
const { VisualPlan } = require('./support.cjs');

test('parseLine reads the mark, the text and the tone', () => {
  assert.deepEqual(VisualPlan.parseLine('+ Saved [info]'), { mark: '+', text: 'Saved', tone: 'info', error: '' });
  assert.deepEqual(VisualPlan.parseLine('plain line'), { mark: '', text: 'plain line', tone: '', error: '' });
  assert.match(VisualPlan.parseLine('x [loud]').error, /unknown tone \[loud\]/);
});

test('vp-flow gives one flow per line with toned steps', () => {
  const parsed = VisualPlan.parseFlow('\n  a > b [bad]\n  c > d\n');
  assert.deepEqual(parsed.errors, []);
  assert.deepEqual(parsed.flows, [[{ text: 'a', tone: '' }, { text: 'b', tone: 'bad' }], [{ text: 'c', tone: '' }, { text: 'd', tone: '' }]]);
  assert.match(VisualPlan.parseFlow('a > [neon]').errors.join(), /unknown tone/);
  assert.match(VisualPlan.parseFlow('').errors.join(), /no flow/);
});

test('vp-branch gives a start flow and one flow per outcome', () => {
  const parsed = VisualPlan.parseBranch('Start [warn]\n-> yes [ok] > go\n-> no');
  assert.deepEqual(parsed.errors, []);
  assert.deepEqual(parsed.start, [{ text: 'Start', tone: 'warn' }]);
  assert.equal(parsed.outcomes.length, 2);
  assert.deepEqual(parsed.outcomes[0][0], { text: 'yes', tone: 'ok' });
  assert.match(VisualPlan.parseBranch('Start\nno arrow').errors.join(), /starts with "->"/);
  assert.match(VisualPlan.parseBranch('Start').errors.join(), /no outcome/);
});

test('vp-vs splits "-" lines into before and "+" lines into after', () => {
  const parsed = VisualPlan.parseVs('- old > broken [bad]\n+ new [ok]');
  assert.deepEqual(parsed.errors, []);
  assert.equal(parsed.before[0][1].tone, 'bad');
  assert.equal(parsed.after[0][0].text, 'new');
  assert.match(VisualPlan.parseVs('+ only after').errors.join(), /no "- " line/);
  assert.match(VisualPlan.parseVs('neither').errors.join(), /start the line/);
});

test('vp-stats takes text values; vp-bar and vp-meter need numbers', () => {
  const stats = VisualPlan.parseStats('12 / 12 | rerun | ok\nOff | gate');
  assert.deepEqual(stats.errors, []);
  assert.deepEqual(stats.rows.map((row) => row.shown), ['12 / 12', 'Off']);
  const bar = VisualPlan.parseBar('1,891 | branches | info\n0.5 | small');
  assert.deepEqual(bar.errors, []);
  assert.deepEqual(bar.rows.map((row) => row.amount), [1891, 0.5]);
  assert.match(VisualPlan.parseBar('many | branches').errors.join(), /"many" is not a number/);
  assert.match(VisualPlan.parseMeter('3 | runs | loud').errors.join(), /unknown tone "loud"/);
  assert.match(VisualPlan.parseMeter('3').errors.join(), /value \| label \| tone/);
});

test('vp-chips and vp-checks read tones and marks', () => {
  assert.deepEqual(VisualPlan.parseChips('One [ok]\nTwo').chips, [{ text: 'One', tone: 'ok' }, { text: 'Two', tone: '' }]);
  const checks = VisualPlan.parseChecks('+ holds\n- fails\n! warns\nplain\nset [info]');
  assert.deepEqual(checks.errors, []);
  assert.deepEqual(checks.checks.map((check) => check.tone), ['ok', 'bad', 'warn', '', 'info']);
});

test('vp-links reads label, url and note, and refuses a script url', () => {
  const parsed = VisualPlan.parseLinks('Run 1 | https://example.com/1 | slow\nRun 2 | ./runs/2.html');
  assert.deepEqual(parsed.errors, []);
  assert.deepEqual(parsed.links[0], { label: 'Run 1', url: 'https://example.com/1', note: 'slow' });
  assert.match(VisualPlan.parseLinks('Bad | javascript:alert(1)').errors.join(), /not an http/);
});

test('vp-dots counts whole dots', () => {
  assert.deepEqual(VisualPlan.parseDots('3 | ok\n2').groups, [{ count: 3, tone: 'ok' }, { count: 2, tone: '' }]);
  assert.match(VisualPlan.parseDots('2.5 | ok').errors.join(), /whole number/);
});

test('renderBlock draws a flow with arrows and tone classes', () => {
  const html = VisualPlan.renderBlock({ kind: 'flow', parsed: VisualPlan.parseFlow('a > b [info]'), attrs: {} });
  assert.match(html, /<span class="fs ">a<\/span><span class="fa" aria-hidden="true">\u2192<\/span><span class="fs here">b<\/span>/);
});

test('openStore waits for a db that resolves after 5 s and uses it', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const db = { doc() {}, collection() {} };
  globalThis.window = { claude: { use: () => new Promise((resolve) => setTimeout(() => resolve(db), 5000)) } };
  t.after(() => { delete globalThis.window; });
  const opened = VisualPlan.openStore('visualplan:test');
  t.mock.timers.tick(5000);
  assert.equal((await opened).kind, 'db');
});
