const { test } = require('node:test');
const assert = require('node:assert/strict');
const { VisualPlan, page } = require('./support.cjs');

const errorsOf = (parts) => VisualPlan.lint(page(parts)).errors;
const assertError = (parts, pattern) => {
  const errors = errorsOf(parts);
  assert.ok(errors.some((message) => pattern.test(message)), `expected ${pattern} in ${JSON.stringify(errors)}`);
};
const row = (cells) => `<vp-row>${cells}</vp-row>`;
const PLAIN_TAIL = '<vp-cell face="Fix"></vp-cell><vp-cell count="1"></vp-cell>';

test('the base page lints clean', () => {
  assert.deepEqual(errorsOf({}), []);
});

test('an unknown vp- element is an error', () => {
  assertError({ rows: row(`<vp-cell face="A"><vp-graph></vp-graph></vp-cell>${PLAIN_TAIL}`) }, /unknown element <vp-graph>/);
});

test('a block line that does not parse is an error', () => {
  assertError({ rows: row(`<vp-cell face="A"><vp-bar><script type="text/plain">lots | runs</script></vp-bar></vp-cell>${PLAIN_TAIL}`) }, /"lots" is not a number/);
  assertError({ rows: row(`<vp-cell face="A"><vp-flow><script type="text/plain">a > b [shiny]</script></vp-flow></vp-cell>${PLAIN_TAIL}`) }, /unknown tone \[shiny\]/);
});

test('a row whose cell count differs from the column count is an error', () => {
  assertError({ rows: row('<vp-cell face="A"></vp-cell><vp-cell face="B"></vp-cell>') }, /2 cells and the grid has 3 columns/);
});

test('an ask with no id, a duplicate id or a duplicate control name is an error', () => {
  const ask = (id, name) => `<vp-ask${id === null ? '' : ` id="${id}"`}><p>Pick one?</p><label><input type="radio" name="${name}" value="a" checked> A</label><label><input type="radio" name="${name}" value="b"> B</label></vp-ask>`;
  assertError({ asks: ask(null, 'pick') }, /needs an id/);
  assertError({ asks: ask('pick', 'one') + ask('pick', 'two') }, /two asks have the id "pick"/);
  assertError({ asks: ask('first', 'shared') + ask('second', 'shared') }, /control name "shared" is used by the ask "first"/);
});

test('a non-top ask without exactly one checked option is an error', () => {
  const ask = (first, second) => `<vp-ask id="pick"><p>Pick one?</p><label><input type="radio" name="pick" value="a"${first}> A</label><label><input type="radio" name="pick" value="b"${second}> B</label></vp-ask>`;
  assertError({ asks: ask('', '') }, /0 checked options/);
  assertError({ asks: ask(' checked', ' checked') }, /2 checked options/);
});

test('a vp-details that is not last, or a second one, is an error', () => {
  const details = '<vp-details><p>raw</p></vp-details>';
  const chips = '<vp-chips><script type="text/plain">x</script></vp-chips>';
  assertError({ rows: row(`<vp-cell face="A">${details}${chips}</vp-cell>${PLAIN_TAIL}`) }, /must be the last child/);
  assertError({ rows: row(`<vp-cell face="A">${chips}${details}${details}</vp-cell>${PLAIN_TAIL}`) }, /this is a second one/);
});

test('two cells with the same id are an error', () => {
  assertError({ rows: row(`<vp-cell face="A" id="same"></vp-cell><vp-cell face="B" id="same"></vp-cell><vp-cell count="1"></vp-cell>`) }, /two cells have the id "same"/);
  assertError({ rows: row(`<vp-cell face="Twin"></vp-cell>${PLAIN_TAIL}`) + row(`<vp-cell face="Twin"></vp-cell>${PLAIN_TAIL}`) }, /two cells have the id "twin.0"/);
});

test('a page with no h1 is an error', () => {
  assertError({ header: '<header></header>' }, /no <h1>/);
});

test('budgets for skimming are warnings, not errors', () => {
  const report = VisualPlan.lint(page({
    header: '<header><h1>Plan</h1></header>',
    rows: row(`<vp-cell face="One two three four five six"></vp-cell>${PLAIN_TAIL}`),
  }));
  assert.deepEqual(report.errors, []);
  assert.ok(report.warnings.some((message) => /<h1> has 1 words/.test(message)));
  assert.ok(report.warnings.some((message) => /has 6 words; keep a face to 5/.test(message)));
});

test('cell ids default to the slug of the row face and the column index', () => {
  const { plan } = VisualPlan.buildPlan(VisualPlan.fromHtml(page({})));
  const cells = plan.grid.bands[0].rows[0].cells;
  assert.deepEqual(cells.map((cell) => cell.id), ['clock-drift.0', 'clock-drift.1', 'clock-drift.2']);
  assert.ok(plan.cards.has('clock-drift.0'));
  assert.equal(cells[1].card, null);
  assert.equal(plan.grid.maxCount, 12);
});
