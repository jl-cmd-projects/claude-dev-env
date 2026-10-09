const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { page, RUNTIME_DIRECTORY } = require('./support.cjs');

const PACK = path.join(RUNTIME_DIRECTORY, 'pack.mjs');
const SKILL_DIRECTORY = path.dirname(RUNTIME_DIRECTORY);
const runPack = (...commandLine) => spawnSync(process.execPath, [PACK, ...commandLine], { encoding: 'utf8' });

test('the template and the example lint with no errors', () => {
  for (const relativePath of ['templates/plan.html', 'examples/flaky-tests.html']) {
    const run = runPack(path.join(SKILL_DIRECTORY, relativePath), '--lint-only');
    assert.equal(run.status, 0, `${relativePath}\n${run.stdout}${run.stderr}`);
    assert.doesNotMatch(run.stdout, /error:/);
  }
});

test('pack inlines the runtime and writes the artifact copy without its document shell', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'visual-plan-'));
  const source = path.join(directory, 'plan.html');
  fs.writeFileSync(source, page({}));
  const run = runPack(source, '--artifact', '--quiet');
  assert.equal(run.status, 0, run.stdout + run.stderr);
  const packed = fs.readFileSync(path.join(directory, 'plan.packed.html'), 'utf8');
  assert.match(packed, /<style data-visualplan>/);
  assert.match(packed, /<script data-visualplan>/);
  assert.doesNotMatch(packed.split('<style data-visualplan>')[0], /<link|<script/);
  const artifact = fs.readFileSync(path.join(directory, 'plan.artifact.html'), 'utf8');
  assert.doesNotMatch(artifact, /<html|<body|<!doctype/i);
  assert.match(artifact, /<title>Test Plan<\/title>/);
});

test('pack refuses to write a page with an error', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'visual-plan-'));
  const source = path.join(directory, 'plan.html');
  fs.writeFileSync(source, page({ header: '<header></header>' }));
  const run = runPack(source);
  assert.equal(run.status, 1);
  assert.match(run.stdout, /error: no <h1>/);
  assert.equal(fs.existsSync(path.join(directory, 'plan.packed.html')), false);
});
