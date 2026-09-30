import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, lstatSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { seedCodexPstackModels } from './seed-codex-pstack-models.mjs';
import { QUESTION_PRESENTATION_BLOCK_END, QUESTION_PRESENTATION_BLOCK_START } from './codex-skill-load-block.mjs';

const QUESTION_GUIDANCE = `${QUESTION_PRESENTATION_BLOCK_START}\nAsk one question.\n${QUESTION_PRESENTATION_BLOCK_END}\n`;

test('fresh Codex home gets the selected roles and hook setting', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    const claudeHome = join(root, '.claude');
    mkdirSync(claudeHome);
    writeFileSync(join(claudeHome, 'CLAUDE.md'), 'Claude guidance\n');

    const paths = seedCodexPstackModels(codexHome);
    const sheet = readFileSync(join(codexHome, 'pstack-models.md'), 'utf8');
    const agents = readFileSync(join(codexHome, 'AGENTS.md'), 'utf8');
    assert.deepEqual(paths, [join(codexHome, 'pstack-models.md'), join(codexHome, 'AGENTS.md')]);
    assert.match(sheet, /^feature, refactoring: gpt-6-sol$/m);
    assert.match(sheet, /^bug-fix: gpt-6-astra$/m);
    assert.match(sheet, /^how explorer: gpt-6-luna$/m);
    assert.match(sheet, /^arena runners: gpt-6-astra, gpt-6-sol, gpt-6-luna$/m);
    assert.match(sheet, /^session hook: on$/m);
    assert.match(agents, /^feature, refactoring: gpt-6-sol$/m);
    assert.doesNotMatch(agents, /^session hook:/m);
    assert.equal(readFileSync(join(claudeHome, 'CLAUDE.md'), 'utf8'), 'Claude guidance\n');
    assert.equal(existsSync(join(claudeHome, 'pstack-models.md')), false);
});

test('existing Codex configuration stays untouched on repeat installs', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    seedCodexPstackModels(codexHome);
    writeFileSync(join(codexHome, 'AGENTS.md'), 'Custom agents\n');

    assert.equal(seedCodexPstackModels(codexHome), null);
    assert.equal(readFileSync(join(codexHome, 'AGENTS.md'), 'utf8'), 'Custom agents\n');
});

test('a failed AGENTS write removes only the sheet created by that attempt', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    const claudeHome = join(root, '.claude');
    mkdirSync(claudeHome);
    writeFileSync(join(claudeHome, 'CLAUDE.md'), 'Existing Claude guidance\n');

    const competingWrite = (agentsPath) => {
        writeFileSync(agentsPath, 'Existing Codex guidance\n');
        throw new Error('AGENTS.md already exists');
    };
    assert.throws(() => seedCodexPstackModels(codexHome, competingWrite), /already exists/);
    assert.equal(existsSync(join(codexHome, 'pstack-models.md')), false);
    assert.equal(readFileSync(join(codexHome, 'AGENTS.md'), 'utf8'), 'Existing Codex guidance\n');
    assert.equal(readFileSync(join(claudeHome, 'CLAUDE.md'), 'utf8'), 'Existing Claude guidance\n');
});

for (const existingFile of ['AGENTS.md', 'pstack-models.md']) {
    test(`partial Codex setup with ${existingFile} is preserved`, (context) => {
        const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
        context.after(() => rmSync(root, { recursive: true, force: true }));
        const codexHome = join(root, '.codex');
        mkdirSync(codexHome);
        writeFileSync(join(codexHome, existingFile), 'Custom configuration\n');

        assert.equal(seedCodexPstackModels(codexHome), null);
        assert.equal(readFileSync(join(codexHome, existingFile), 'utf8'), 'Custom configuration\n');
        assert.equal(existsSync(join(codexHome, existingFile === 'AGENTS.md' ? 'pstack-models.md' : 'AGENTS.md')), false);
    });
}

test('a question-only Codex file receives model defaults and keeps its block', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    mkdirSync(codexHome);
    writeFileSync(join(codexHome, 'AGENTS.md'), QUESTION_GUIDANCE);

    const paths = seedCodexPstackModels(codexHome);

    assert.deepEqual(paths, [join(codexHome, 'pstack-models.md'), join(codexHome, 'AGENTS.md')]);
    assert.match(readFileSync(join(codexHome, 'pstack-models.md'), 'utf8'), /^session hook: on$/m);
    const agents = readFileSync(join(codexHome, 'AGENTS.md'), 'utf8');
    assert.match(agents, /^feature, refactoring: gpt-6-sol$/m);
    assert.ok(agents.endsWith(QUESTION_GUIDANCE));
});

test('a question block with personal notes does not trigger model seeding', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    mkdirSync(codexHome);
    writeFileSync(join(codexHome, 'AGENTS.md'), `${QUESTION_GUIDANCE}My notes\n`);

    assert.equal(seedCodexPstackModels(codexHome), null);
    assert.equal(existsSync(join(codexHome, 'pstack-models.md')), false);
});

test('a linked question-only Codex file does not trigger model seeding', (context) => {
    const root = mkdtempSync(join(tmpdir(), 'cde-pstack-models-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    const linkedGuidancePath = join(root, 'linked-guidance.md');
    mkdirSync(codexHome);
    writeFileSync(linkedGuidancePath, QUESTION_GUIDANCE);
    symlinkSync(linkedGuidancePath, join(codexHome, 'AGENTS.md'));

    assert.equal(seedCodexPstackModels(codexHome), null);
    assert.equal(lstatSync(join(codexHome, 'AGENTS.md')).isSymbolicLink(), true);
    assert.equal(readFileSync(linkedGuidancePath, 'utf8'), QUESTION_GUIDANCE);
});
