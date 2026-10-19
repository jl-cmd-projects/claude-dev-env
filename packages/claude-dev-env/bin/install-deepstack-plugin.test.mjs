import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { chmodSync, existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    DEEPSTACK_MARKETPLACE_REPOSITORY,
    DEEPSTACK_SKILL_RELATIVE_PATH,
    DEEPSTACK_PLUGIN_IDENTIFIER,
    DEEPSTACK_PLUGIN_SPEC,
    deepStackCloneUrl,
    deepStackInstallPlan,
    deepStackCursorSessionCommand,
    installDeepStackCursor,
    installDeepStackForHosts,
    mergeDeepStackCursorHooks,
    removeDeepStackCursorHooks,
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

test('cursor hooks are one native sessionStart entry and one native beforeSubmitPrompt entry', () => {
    const legacySessionGroup = {
        matcher: 'startup|resume|clear|compact',
        hooks: [{ type: 'command', command: "'C:\\Users\\dev\\.cursor\\plugins\\deepstack\\hooks\\session-start.sh' cursor" }],
    };
    const commands = {
        sessionCommand: "'/cursor/plugins/deepstack/hooks/session-start.sh' cursor",
        firstTaskCommand: "python3 '/claude/hooks/session/deepen_first_prompt.py'",
    };
    const merged = mergeDeepStackCursorHooks({
        hooks: {
            SessionStart: [legacySessionGroup, legacySessionGroup, legacySessionGroup],
            UserPromptSubmit: [{ matcher: '', hooks: [{ type: 'command', command: 'python3 /old/deepen_first_prompt.py', timeout: 10 }] }],
            preToolUse: [],
        },
    }, commands);
    assert.deepEqual(merged, {
        version: 1,
        hooks: {
            sessionStart: [{ command: commands.sessionCommand, timeout: 10 }],
            beforeSubmitPrompt: [{ command: commands.firstTaskCommand, timeout: 10 }],
            preToolUse: [],
        },
    });
    assert.deepEqual(mergeDeepStackCursorHooks(merged, commands), merged);
});

test('the Windows session command runs the PowerShell script, other platforms the shell script', () => {
    const root = mkdtempSync(join(tmpdir(), 'deepstack-cursor-'));
    try {
        mkdirSync(join(root, 'hooks'), { recursive: true });
        writeFileSync(join(root, 'hooks', 'session-start.ps1'), 'param()\n');
        const forwardSlashed = pathValue => `"${pathValue.replace(/\\/g, '/')}"`;
        assert.match(deepStackCursorSessionCommand(root, forwardSlashed, 'win32'), /^powershell -NoProfile -ExecutionPolicy Bypass -File ".*hooks\/session-start\.ps1" cursor$/);
        assert.match(deepStackCursorSessionCommand(root, forwardSlashed, 'linux'), /hooks\/session-start\.sh" cursor$/);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

test('the cursor copy writes the skill and both native hook commands, and removal takes out only those', () => {
    const root = mkdtempSync(join(tmpdir(), 'deepstack-cursor-'));
    try {
        const source = join(root, 'source');
        mkdirSync(join(source, 'skills', 'deepstack-mode'), { recursive: true });
        mkdirSync(join(source, 'hooks'), { recursive: true });
        writeFileSync(join(source, 'skills', 'deepstack-mode', 'SKILL.md'), 'DeepStack intake\n');
        writeFileSync(join(source, 'hooks', 'session-start.sh'), '#!/bin/sh\n');
        const cursorDirectory = join(root, '.cursor');
        mkdirSync(cursorDirectory, { recursive: true });
        writeFileSync(join(cursorDirectory, 'hooks.json'), JSON.stringify({ version: 1, hooks: { stop: [{ command: './user-stop.sh' }] } }));
        const outcome = installDeepStackCursor({
            cursorDirectory,
            pluginSourceDirectory: source,
            firstTaskHookPath: join(root, '.agents', 'hooks', 'session', 'deepen_first_prompt.py'),
            pythonCommand: '/usr/bin/python3.12',
            platform: 'linux',
        });
        assert.equal(outcome.status, 'installed');
        assert.equal(
            readFileSync(join(cursorDirectory, 'plugins', 'deepstack', 'skills', 'deepstack-mode', 'SKILL.md'), 'utf8'),
            'DeepStack intake\n',
        );
        const hooks = JSON.parse(readFileSync(join(cursorDirectory, 'hooks.json'), 'utf8'));
        assert.equal(hooks.version, 1);
        assert.equal(hooks.hooks.sessionStart.length, 1);
        assert.match(hooks.hooks.sessionStart[0].command, /session-start\.sh' cursor$/);
        assert.match(hooks.hooks.beforeSubmitPrompt[0].command, /^\/usr\/bin\/python3\.12 '.*deepen_first_prompt\.py'$/);
        removeDeepStackCursorHooks(cursorDirectory);
        assert.deepEqual(
            JSON.parse(readFileSync(join(cursorDirectory, 'hooks.json'), 'utf8')),
            { version: 1, hooks: { stop: [{ command: './user-stop.sh' }] } },
        );
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

const absentHostRunner = () => ({ status: null, stderr: '', error: { code: 'ENOENT' } });

function writeClonedPlugin(cloneDirectory) {
    const pluginDirectory = join(cloneDirectory, 'plugins', 'deepstack');
    mkdirSync(join(pluginDirectory, 'skills', 'deepstack-mode'), { recursive: true });
    writeFileSync(join(pluginDirectory, DEEPSTACK_SKILL_RELATIVE_PATH), '# DeepStack\n');
    mkdirSync(join(cloneDirectory, '.git', 'objects', 'pack'), { recursive: true });
    const packPath = join(cloneDirectory, '.git', 'objects', 'pack', 'pack-1.pack');
    writeFileSync(packPath, 'pack');
    chmodSync(packPath, 0o444);
    return pluginDirectory;
}

test('the temporary clone is removed once the Cursor copy is written', () => {
    const root = mkdtempSync(join(tmpdir(), 'deepstack-clone-'));
    try {
        const cloneParentDirectory = join(root, 'temp');
        mkdirSync(cloneParentDirectory);
        const cursorDirectory = join(root, 'cursor');
        let clonedInto = null;
        const outcome = installDeepStackForHosts({
            claudeRoot: join(root, 'claude'),
            codexHome: join(root, 'codex'),
            cursorDirectory,
            firstTaskHookPath: join(root, 'hooks', 'deepen_first_prompt.py'),
            environment: {},
            cloneParentDirectory,
        }, {
            runCommand: absentHostRunner,
            cloneRepository: cloneDirectory => {
                clonedInto = cloneDirectory;
                return writeClonedPlugin(cloneDirectory);
            },
        });
        assert.equal(outcome.cursor.status, 'installed');
        assert.ok(clonedInto.startsWith(cloneParentDirectory));
        assert.ok(existsSync(join(cursorDirectory, 'plugins', 'deepstack', DEEPSTACK_SKILL_RELATIVE_PATH)));
        assert.deepEqual(readdirSync(cloneParentDirectory), []);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

test('a failed clone leaves no temporary folder behind', () => {
    const root = mkdtempSync(join(tmpdir(), 'deepstack-clone-'));
    try {
        const cloneParentDirectory = join(root, 'temp');
        mkdirSync(cloneParentDirectory);
        const outcome = installDeepStackForHosts({
            claudeRoot: join(root, 'claude'),
            codexHome: join(root, 'codex'),
            cursorDirectory: join(root, 'cursor'),
            firstTaskHookPath: join(root, 'hooks', 'deepen_first_prompt.py'),
            environment: {},
            cloneParentDirectory,
        }, { runCommand: absentHostRunner, cloneRepository: () => null });
        assert.equal(outcome.cursor.status, 'failed');
        assert.deepEqual(readdirSync(cloneParentDirectory), []);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});
