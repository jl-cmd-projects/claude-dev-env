import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import {
    mkdtempSync,
    mkdirSync,
    writeFileSync,
    readFileSync,
    existsSync,
    copyFileSync,
    rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import {
    resolveInstallRoot,
} from './resolve-install-root.mjs';
import {
    DEFAULT_CURSOR_DIRECTORY_NAME,
    CURSOR_RULES_DIRECTORY_NAME,
} from './install-constants.mjs';

const THIS_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const INSTALLER_PATH = join(THIS_DIRECTORY, 'install.mjs');
const PACKAGE_DIRECTORY = dirname(THIS_DIRECTORY);

function runInstaller(homeDirectory, extraArguments, environmentOverrides = {}) {
    return execFileSync('node', [INSTALLER_PATH, ...extraArguments], {
        cwd: PACKAGE_DIRECTORY,
        encoding: 'utf8',
        env: {
            ...process.env,
            CDE_INSTALL_PSTACK: '0',
            CDE_INSTALL_USAGE_WRAPUP: '0',
            CDE_INSTALL_SUBAGENT_MODELS: '0',
            HOME: homeDirectory,
            USERPROFILE: homeDirectory,
            CODEX_HOME: join(homeDirectory, '.codex'),
            CLAUDE_CONFIG_DIR: join(homeDirectory, '.claude'),
            GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
            ...environmentOverrides,
        },
    });
}

test('a reinstall moves the Cursor rules an older install generated and keeps a local mdc', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-install-'));
    try {
        runInstaller(homeDirectory, []);
        const cursorDirectory = join(homeDirectory, DEFAULT_CURSOR_DIRECTORY_NAME);
        const rulesDirectory = join(cursorDirectory, CURSOR_RULES_DIRECTORY_NAME);
        const generatedRulePath = join(rulesDirectory, 'asd-ste100-language.mdc');
        const syncManifestPath = join(cursorDirectory, '.sync-manifest.json');
        const localRulePath = join(rulesDirectory, 'user-local.mdc');
        mkdirSync(rulesDirectory, { recursive: true });
        writeFileSync(generatedRulePath, 'generated\n');
        writeFileSync(syncManifestPath, '{}\n');
        writeFileSync(localRulePath, 'keep-me\n');
        const manifestPath = join(homeDirectory, '.claude', '.claude-dev-env-manifest.json');
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
        manifest.files.push(generatedRulePath, syncManifestPath);
        writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');

        runInstaller(homeDirectory, []);

        assert.equal(existsSync(generatedRulePath), false);
        assert.equal(existsSync(syncManifestPath), false);
        assert.equal(readFileSync(localRulePath, 'utf8'), 'keep-me\n');
        const reinstalledManifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
        assert.equal(reinstalledManifest.files.includes(generatedRulePath), false);
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('--only journal is rejected before the policy is seeded; --only core seeds it and writes no Cursor rules', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-groups-'));
    try {
        const cursorRulesDirectory = join(
            homeDirectory,
            DEFAULT_CURSOR_DIRECTORY_NAME,
            CURSOR_RULES_DIRECTORY_NAME,
        );
        const policyPath = join(homeDirectory, '.agents', 'rules', 'subagent-model-policy.json');
        assert.throws(
            () => runInstaller(homeDirectory, ['--only', 'journal']),
            error => error.status === 1 && /Unknown group\(s\): journal/.test(error.stderr),
        );
        assert.equal(existsSync(policyPath), false);

        runInstaller(homeDirectory, ['--only', 'core']);
        assert.equal(existsSync(policyPath), true);
        assert.equal(existsSync(cursorRulesDirectory), false);
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});


test('seeds one editable policy and one native Codex routing hook', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-install-'));
    try {
        const resolution = resolveInstallRoot({
            homeDirectory,
            environment: {},
            explicitTarget: null,
        });
        const policyPath = join(resolution.agentsHome, 'rules', 'subagent-model-policy.json');
        const installedRulesPolicyPath = join(
            resolution.managedRoot,
            'rules',
            'subagent-model-policy.json',
        );
        const codexHooksPath = join(homeDirectory, '.codex', 'hooks.json');

        runInstaller(homeDirectory, ['--only', 'core']);

        assert.equal(existsSync(policyPath), true);
        assert.equal(existsSync(installedRulesPolicyPath), false);
        const firstCodexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        const firstRoutingGroups = firstCodexHooks.hooks.PreToolUse.filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        assert.equal(firstRoutingGroups.length, 1);
        assert.equal(firstRoutingGroups[0].hooks.length, 3);
        assert.match(firstRoutingGroups[0].hooks[0].command, /subagent_model_routing\.mjs/);
        assert.match(firstRoutingGroups[0].hooks[1].command, /spawn_readiness_hook\.py/);
        assert.match(firstRoutingGroups[0].hooks[2].command, /spawn_oversight_hook\.py/);
        const firstSpawnPromptGroups = firstCodexHooks.hooks.PreToolUse.filter(
            group => group.matcher === 'Agent|Task',
        );
        assert.equal(firstSpawnPromptGroups.length, 1);
        assert.match(firstSpawnPromptGroups[0].hooks[0].command, /skill_loaded_reminder\.py/);
        assert.deepEqual(Object.keys(firstCodexHooks.hooks), ['PreToolUse']);
        assert.equal(
            firstCodexHooks.hooks.PreToolUse.some(group => group.matcher === 'Write|Edit|MultiEdit|apply_patch'),
            false,
        );

        const editedPolicy = '{"schemaVersion":1,"edited":true}\n';
        writeFileSync(policyPath, editedPolicy);
        firstCodexHooks.hooks.PreToolUse.push({
            matcher: 'custom',
            hooks: [{ type: 'command', command: 'python user-hook.py' }],
        });
        writeFileSync(codexHooksPath, JSON.stringify(firstCodexHooks, null, 2) + '\n');

        runInstaller(homeDirectory, ['--only', 'core']);

        assert.equal(readFileSync(policyPath, 'utf8'), editedPolicy);
        const secondCodexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        assert.equal(
            secondCodexHooks.hooks.PreToolUse.filter(
                group => group.matcher === 'multi_agent_v1__spawn_agent',
            ).length,
            1,
        );
        assert.equal(
            secondCodexHooks.hooks.PreToolUse.some(
                group => group.matcher === 'custom'
                    && group.hooks.some(hook => hook.command === 'python user-hook.py'),
            ),
            true,
        );
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('reinstall moves the old routing hook and keeps user hooks', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-hook-upgrade-'));
    try {
        const resolution = resolveInstallRoot({
            homeDirectory,
            environment: {},
            explicitTarget: null,
        });
        const codexHooksPath = join(homeDirectory, '.codex', 'hooks.json');
        const manifestPath = resolution.manifestFilePath;
        const routingHookPath = join(
            homeDirectory,
            '.codex',
            'hooks',
            'routing',
            'subagent_model_routing.mjs',
        );
        const oldRoutingHookPath = join(
            homeDirectory,
            '.codex',
            'hooks',
            'blocking',
            'subagent_model_routing.mjs',
        );

        runInstaller(homeDirectory, []);
        const firstCodexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        const firstRoutingGroup = firstCodexHooks.hooks.PreToolUse.find(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        firstRoutingGroup.hooks[0].command = firstRoutingGroup.hooks[0].command.replace(
            /routing([\\/])subagent_model_routing\.mjs$/,
            'blocking$1subagent_model_routing.mjs',
        );
        firstCodexHooks.hooks.PreToolUse.push({
            matcher: 'custom',
            hooks: [{ type: 'command', command: 'node user-hook.mjs' }],
        });
        writeFileSync(codexHooksPath, JSON.stringify(firstCodexHooks, null, 2) + '\n');
        copyFileSync(routingHookPath, oldRoutingHookPath);
        rmSync(routingHookPath);

        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
        manifest.files = manifest.files.map(file => file.replace(
            /([\\/])routing([\\/]subagent_model_routing\.mjs)$/,
            '$1blocking$2',
        ));
        writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');

        runInstaller(homeDirectory, []);

        const secondCodexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        const routingGroups = secondCodexHooks.hooks.PreToolUse.filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        assert.equal(routingGroups.length, 1);
        assert.match(routingGroups[0].hooks[0].command, /[\\/]hooks[\\/]routing[\\/]subagent_model_routing\.mjs/);
        assert.doesNotMatch(
            JSON.stringify(secondCodexHooks),
            /[\\/]hooks[\\/]blocking[\\/]subagent_model_routing\.mjs/,
        );
        assert.equal(existsSync(routingHookPath), true);
        assert.equal(existsSync(oldRoutingHookPath), false);
        assert.equal(
            secondCodexHooks.hooks.PreToolUse.some(
                group => group.matcher === 'custom'
                    && group.hooks.some(hook => hook.command === 'node user-hook.mjs'),
            ),
            true,
        );
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('Codex reinstall removes omitted package hooks and preserves user configuration', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-codex-migration-'));
    try {
        const codexHome = join(homeDirectory, 'custom-codex');
        const codexHooksPath = join(codexHome, 'hooks.json');
        const configPath = join(codexHome, 'config.toml');
        const disabledConfig = '[features]\nhooks = false\n';
        const allLegacyRegistrations = [
            ['PreToolUse', 'Edit', '.claude', 'blocking/pre_tool_use_dispatcher.py'],
            ['PreToolUse', 'Bash', '.agents', 'blocking/bash_pre_tool_use_dispatcher.py'],
            ['SessionStart', '*', 'custom-codex', 'session/issue_tracker_session_starter.py'],
            ['Stop', '*', '.claude', 'session/skill_loaded_reminder.py'],
            ['SessionEnd', '*', 'custom-codex', 'lifecycle/session_end_cleanup.py'],
        ];
        const hooksByEvent = {};
        for (const [event, matcher, root, script] of allLegacyRegistrations) {
            hooksByEvent[event] ??= [];
            hooksByEvent[event].push({
                matcher,
                metadata: 'keep-group',
                hooks: [
                    { type: 'command', command: `python "${join(homeDirectory, root, 'hooks', script)}"` },
                    { type: 'command', command: `user-${event}-${matcher}`, timeout: 7 },
                ],
            });
        }
        const foreignCommand = `python "${join(homeDirectory, 'foreign', '.claude', 'hooks', 'blocking', 'pre_tool_use_dispatcher.py')}"`;
        hooksByEvent.PreToolUse.push({ matcher: 'foreign', hooks: [{ type: 'command', command: foreignCommand }] });
        const suffixCommand = `python "${join(codexHome, 'hooks', 'blocking', 'pre_tool_use_dispatcher.py.backup')}"`;
        hooksByEvent.PreToolUse.push({ matcher: 'suffix', hooks: [{ type: 'command', command: suffixCommand }] });
        hooksByEvent.CustomEvent = { metadata: 'keep-event' };
        const expectedUserHooks = JSON.parse(JSON.stringify(hooksByEvent));
        for (const eachGroup of Object.values(expectedUserHooks).flat()) {
            if (eachGroup.hooks && eachGroup.metadata) eachGroup.hooks.shift();
        }
        hooksByEvent.LegacyValidator = [{ hooks: [{ type: 'command', command: 'python -c "sys.path.insert(0, __claude_dev_env_managed_hooks__); from validators.run_all_validators import main; main()"' }] }];
        mkdirSync(codexHome, { recursive: true });
        writeFileSync(configPath, disabledConfig);
        writeFileSync(codexHooksPath, JSON.stringify({ enabled: false, metadata: 'keep-file', hooks: hooksByEvent }));

        runInstaller(homeDirectory, ['--only', 'core'], { CODEX_HOME: codexHome });

        const migratedHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        const allSpawnGroups = migratedHooks.hooks.PreToolUse.filter(eachGroup =>
            ['Agent|Task', 'multi_agent_v1__spawn_agent'].includes(eachGroup.matcher));
        assert.equal(allSpawnGroups.length, 2);
        migratedHooks.hooks.PreToolUse = migratedHooks.hooks.PreToolUse.filter(eachGroup => !allSpawnGroups.includes(eachGroup));
        assert.deepEqual(migratedHooks, { enabled: false, metadata: 'keep-file', hooks: expectedUserHooks });
        assert.equal(readFileSync(configPath, 'utf8'), disabledConfig);
        const firstInstall = readFileSync(codexHooksPath, 'utf8');
        runInstaller(homeDirectory, ['--only', 'core'], { CODEX_HOME: codexHome });
        assert.equal(readFileSync(codexHooksPath, 'utf8'), firstInstall);
        const claudeSettings = JSON.parse(readFileSync(join(homeDirectory, '.claude', 'settings.json'), 'utf8'));
        assert.ok(claudeSettings.hooks.SessionStart.length > 0);
        assert.ok(claudeSettings.hooks.PreToolUse.some(eachGroup => eachGroup.matcher === 'Bash'));
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('uninstall removes the routing hook and keeps a Codex user hook', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-uninstall-'));
    try {
        const profileRoot = join(homeDirectory, 'named-profile');
        const codexHooksPath = join(profileRoot, '.codex', 'hooks.json');
        const targetArguments = ['--target', profileRoot];
        runInstaller(homeDirectory, [...targetArguments, '--only', 'core']);
        const codexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        codexHooks.hooks.PreToolUse.push({
            matcher: 'custom',
            hooks: [{ type: 'command', command: 'python user-hook.py' }],
        });
        writeFileSync(codexHooksPath, JSON.stringify(codexHooks, null, 2) + '\n');

        runInstaller(homeDirectory, [...targetArguments, '--uninstall']);

        const remainingHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
        assert.equal(
            remainingHooks.hooks.PreToolUse.some(group => group.matcher === 'multi_agent_v1__spawn_agent'),
            false,
        );
        assert.equal(
            remainingHooks.hooks.PreToolUse.some(
                group => group.matcher === 'custom'
                    && group.hooks.some(hook => hook.command === 'python user-hook.py'),
            ),
            true,
        );
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('malformed Codex hooks restore the staged install', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-malformed-'));
    try {
        const codexHooksPath = join(homeDirectory, '.codex', 'hooks.json');
        const claudeSettingsPath = join(homeDirectory, '.claude', 'settings.json');
        const originalCodexHooks = '{ malformed\n';
        const originalClaudeSettings = '{"hooks":{"PreToolUse":[{"matcher":"user","hooks":[{"type":"command","command":"user-hook"}]}]}}\n';
        mkdirSync(dirname(codexHooksPath), { recursive: true });
        mkdirSync(dirname(claudeSettingsPath), { recursive: true });
        writeFileSync(codexHooksPath, originalCodexHooks);
        writeFileSync(claudeSettingsPath, originalClaudeSettings);

        assert.throws(
            () => runInstaller(homeDirectory, ['--only', 'core']),
            error => error.status === 1,
        );
        assert.equal(readFileSync(codexHooksPath, 'utf8'), originalCodexHooks);
        assert.equal(readFileSync(claudeSettingsPath, 'utf8'), originalClaudeSettings);
        assert.equal(existsSync(join(homeDirectory, '.claude', 'hooks')), false);
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('malformed Codex hooks restore an uninstall', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-uninstall-malformed-'));
    try {
        runInstaller(homeDirectory, ['--only', 'core']);
        const codexHooksPath = join(homeDirectory, '.codex', 'hooks.json');
        const manifestPath = join(homeDirectory, '.claude', '.claude-dev-env-manifest.json');
        const managedHookPath = join(
            homeDirectory,
            '.claude',
            'hooks',
            'routing',
            'subagent_model_routing.mjs',
        );
        writeFileSync(codexHooksPath, '{ malformed\n');

        assert.throws(
            () => runInstaller(homeDirectory, ['--uninstall']),
            error => error.status === 1,
        );
        assert.equal(existsSync(manifestPath), true);
        assert.equal(existsSync(managedHookPath), true);
        assert.equal(readFileSync(codexHooksPath, 'utf8'), '{ malformed\n');
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('two profiles keep separate Codex routing hooks', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-profiles-'));
    try {
        const profileRoot = join(homeDirectory, 'named-profile');
        const mainCodexHooksPath = join(homeDirectory, '.codex', 'hooks.json');
        const profileCodexHooksPath = join(profileRoot, '.codex', 'hooks.json');
        runInstaller(homeDirectory, ['--only', 'core']);
        runInstaller(homeDirectory, ['--target', profileRoot, '--only', 'core']);

        const mainCodexHooks = JSON.parse(readFileSync(mainCodexHooksPath, 'utf8'));
        const profileCodexHooks = JSON.parse(readFileSync(profileCodexHooksPath, 'utf8'));
        const mainRoutingGroups = (mainCodexHooks.hooks?.PreToolUse ?? []).filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        const profileRoutingGroups = profileCodexHooks.hooks.PreToolUse.filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        assert.equal(mainRoutingGroups.length, 1);
        assert.equal(profileRoutingGroups.length, 1);
        assert.match(mainRoutingGroups[0].hooks[0].command, /[\\/]\.codex[\\/]hooks[\\/]routing[\\/]subagent_model_routing\.mjs/);
        assert.match(profileRoutingGroups[0].hooks[0].command, /named-profile[\\/]\.codex[\\/]hooks[\\/]routing[\\/]subagent_model_routing\.mjs/);
        assert.notEqual(mainRoutingGroups[0].hooks[0].command, profileRoutingGroups[0].hooks[0].command);

        const profileHookPath = join(
            profileRoot,
            '.codex',
            'hooks',
            'routing',
            'subagent_model_routing.mjs',
        );
        const profileHookResponse = JSON.parse(execFileSync(
            'node',
            [profileHookPath],
            {
                encoding: 'utf8',
                input: JSON.stringify({
                    tool_name: 'multi_agent_v1__spawn_agent',
                    tool_input: { model: 'Terra', reasoning_effort: 'medium' },
                }),
            },
        ));
        assert.equal(
            profileHookResponse.hookSpecificOutput.updatedInput.model,
            'gpt-5.6-luna',
        );
        assert.equal(
            profileHookResponse.hookSpecificOutput.updatedInput.reasoning_effort,
            'xhigh',
        );
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('uninstalling one profile keeps routing for another installed profile', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-routing-profile-uninstall-'));
    try {
        const profileRoot = join(homeDirectory, 'named-profile');
        const mainCodexHooksPath = join(homeDirectory, '.codex', 'hooks.json');
        const profileCodexHooksPath = join(profileRoot, '.codex', 'hooks.json');
        runInstaller(homeDirectory, ['--only', 'core']);
        runInstaller(homeDirectory, ['--target', profileRoot, '--only', 'core']);
        runInstaller(homeDirectory, ['--uninstall']);

        const mainCodexHooks = JSON.parse(readFileSync(mainCodexHooksPath, 'utf8'));
        const profileCodexHooks = JSON.parse(readFileSync(profileCodexHooksPath, 'utf8'));
        const mainRoutingGroups = (mainCodexHooks.hooks?.PreToolUse ?? []).filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        const profileRoutingGroups = profileCodexHooks.hooks.PreToolUse.filter(
            group => group.matcher === 'multi_agent_v1__spawn_agent',
        );
        assert.equal(mainRoutingGroups.length, 0);
        assert.equal(profileRoutingGroups.length, 1);
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

test('a blocked shared rule destination fails the install and keeps the existing file', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-pstack-rollback-'));
    try {
        const sharedRulesPath = join(homeDirectory, '.agents', 'rules');
        mkdirSync(dirname(sharedRulesPath), { recursive: true });
        writeFileSync(sharedRulesPath, 'keep-existing-file');
        assert.throws(() => runInstaller(homeDirectory, ['--only', 'core']));
        assert.equal(readFileSync(sharedRulesPath, 'utf8'), 'keep-existing-file');
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});

