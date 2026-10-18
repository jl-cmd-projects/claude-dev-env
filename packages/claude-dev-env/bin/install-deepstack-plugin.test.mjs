import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    DEEPSTACK_MARKETPLACE_REPOSITORY,
    DEEPSTACK_PLUGIN_IDENTIFIER,
    DEEPSTACK_PLUGIN_SPEC,
    deepStackCloneUrl,
    deepStackInstallPlan,
    installDeepStackCursor,
    installDeepStackForHosts,
    mergeDeepStackCursorHooks,
} from './install-deepstack-plugin.mjs';
import { marketplacePluginsPlan, shouldInstallMarketplacePlugin } from './install-pstack-plugin.mjs';

test('Claude and Codex plans name jl-cmd-projects/DeepStack', () => {
    const plan = deepStackInstallPlan();
    assert.deepEqual(plan.claude.commands, [
        ['plugin', 'marketplace', 'add', DEEPSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'install', DEEPSTACK_PLUGIN_IDENTIFIER],
    ]);
    assert.deepEqual(plan.codex.commands, [
        ['plugin', 'marketplace', 'add', DEEPSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'add', DEEPSTACK_PLUGIN_IDENTIFIER],
    ]);
    assert.equal(DEEPSTACK_MARKETPLACE_REPOSITORY, 'jl-cmd-projects/DeepStack');
    assert.equal(deepStackCloneUrl(), 'https://github.com/jl-cmd-projects/DeepStack.git');
    assert.equal(plan.cursor.skillRelativePath, 'skills/deepstack-mode/SKILL.md');
    assert.equal(plan.cursor.firstTaskHookName, 'deepen_first_prompt.py');
    assert.throws(() => marketplacePluginsPlan([DEEPSTACK_PLUGIN_SPEC], 'cursor'), /cursor/);
});

test('cursor hooks keep the session hook and the first-task gate', () => {
    const merged = mergeDeepStackCursorHooks({ hooks: { PreToolUse: [] } }, {
        sessionCommand: "'/cursor/plugins/deepstack/hooks/session-start.sh' cursor",
        firstTaskCommand: "python3 '/claude/hooks/session/deepen_first_prompt.py'",
    });
    assert.deepEqual(Object.keys(merged.hooks).sort(), ['PreToolUse', 'SessionStart', 'UserPromptSubmit']);
    const text = JSON.stringify(merged);
    assert.match(text, /session-start\.sh/);
    assert.match(text, /deepen_first_prompt\.py/);
});

test('the cursor copy writes the skill and both hook commands', () => {
    const root = mkdtempSync(join(tmpdir(), 'deepstack-cursor-'));
    try {
        const source = join(root, 'source');
        mkdirSync(join(source, 'skills', 'deepstack-mode'), { recursive: true });
        mkdirSync(join(source, 'hooks'), { recursive: true });
        writeFileSync(join(source, 'skills', 'deepstack-mode', 'SKILL.md'), 'DeepStack intake\n');
        writeFileSync(join(source, 'hooks', 'session-start.sh'), '#!/bin/sh\n');
        const cursorDirectory = join(root, '.cursor');
        const outcome = installDeepStackCursor({
            cursorDirectory,
            pluginSourceDirectory: source,
            firstTaskHookPath: join(root, '.agents', 'hooks', 'session', 'deepen_first_prompt.py'),
        });
        assert.equal(outcome.status, 'installed');
        assert.equal(
            readFileSync(join(cursorDirectory, 'plugins', 'deepstack', 'skills', 'deepstack-mode', 'SKILL.md'), 'utf8'),
            'DeepStack intake\n',
        );
        const hooks = JSON.parse(readFileSync(join(cursorDirectory, 'hooks.json'), 'utf8'));
        const text = JSON.stringify(hooks);
        assert.match(text, /session-start\.sh/);
        assert.match(text, /deepen_first_prompt\.py/);
        assert.equal(hooks.hooks.SessionStart[0].hooks[0].command.endsWith(' cursor'), true);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

test('a missing plugin tree fails the cursor copy', () => {
    const outcome = installDeepStackCursor({
        cursorDirectory: '/tmp/unused-cursor',
        pluginSourceDirectory: null,
        firstTaskHookPath: '/tmp/deepen_first_prompt.py',
    });
    assert.equal(outcome.status, 'failed');
    assert.match(outcome.warning, /jl-cmd-projects\/DeepStack/);
});

test('--no-deepstack and CDE_INSTALL_DEEPSTACK=0 skip the install', () => {
    assert.equal(shouldInstallMarketplacePlugin(DEEPSTACK_PLUGIN_SPEC, ['--no-deepstack'], {}), false);
    assert.equal(
        shouldInstallMarketplacePlugin(DEEPSTACK_PLUGIN_SPEC, [], { CDE_INSTALL_DEEPSTACK: '0' }),
        false,
    );
    const skipped = installDeepStackForHosts({
        argumentList: ['--no-deepstack'],
        environment: {},
        allowClone: false,
    });
    assert.equal(skipped.status, 'skipped');
    assert.equal(skipped.cursor.status, 'skipped');
});
