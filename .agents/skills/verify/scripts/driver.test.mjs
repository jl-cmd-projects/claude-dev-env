import test from 'node:test';
import assert from 'node:assert/strict';

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { inspectInstalledGuidance, resolveDriverPaths } from './driver.mjs';

function withInstalledHome(guidanceText, allInstalledRelativePaths, inspect) {
    const home = mkdtempSync(join(tmpdir(), 'cde-guidance-'));
    try {
        const claudeHome = join(home, '.claude');
        const guidancePath = join(home, '.agents', 'AGENTS.md');
        mkdirSync(join(home, '.agents'), { recursive: true });
        writeFileSync(guidancePath, guidanceText);
        for (const eachRelativePath of allInstalledRelativePaths) {
            const installedPath = join(claudeHome, ...eachRelativePath.split('/'));
            mkdirSync(join(installedPath, '..'), { recursive: true });
            writeFileSync(installedPath, '# guide\n');
        }
        return inspect(inspectInstalledGuidance(guidancePath, claudeHome));
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
}

const TRUNK_TEXT = [
    '- **Prose** ([`~/.claude/docs/agents-guidance/prose.md`](docs/agents-guidance/prose.md)). Read it.',
    'No PR until proven',
].join('\n');

test('inspectInstalledGuidance should pass when the rule is present and every pointed-to file is installed', () => {
    withInstalledHome(TRUNK_TEXT, ['docs/agents-guidance/prose.md'], (result) => {
        assert.equal(result.hasNoPrRule, true);
        assert.equal(result.allPointerPaths.length, 1);
        assert.deepEqual(result.allMissingPaths, []);
    });
});

test('inspectInstalledGuidance should name a pointed-to file the install did not write', () => {
    withInstalledHome(TRUNK_TEXT, [], (result) => {
        assert.equal(result.allMissingPaths.length, 1);
        assert.match(result.allMissingPaths[0].replaceAll('\\', '/'), /docs\/agents-guidance\/prose\.md$/);
    });
});

test('inspectInstalledGuidance should report a guidance file without the No PR until proven rule', () => {
    withInstalledHome('- **Status.** Changed.', [], (result) => {
        assert.equal(result.hasNoPrRule, false);
    });
});

test('resolveDriverPaths should reach the repository root from the skill scripts directory', () => {
    const paths = resolveDriverPaths('C:/workspace/.agents/skills/verify/scripts');

    assert.equal(paths.repositoryRoot.replaceAll('\\', '/'), 'C:/workspace');
});

test('resolveDriverPaths should point the package root at the published package', () => {
    const paths = resolveDriverPaths('C:/workspace/.agents/skills/verify/scripts');

    assert.equal(
        paths.packageRoot.replaceAll('\\', '/'),
        'C:/workspace/packages/claude-dev-env',
    );
});

test('resolveDriverPaths should name the installer entry point inside the package', () => {
    const paths = resolveDriverPaths('C:/workspace/.agents/skills/verify/scripts');

    assert.equal(
        paths.installEntry.replaceAll('\\', '/'),
        'C:/workspace/packages/claude-dev-env/bin/install.mjs',
    );
});
