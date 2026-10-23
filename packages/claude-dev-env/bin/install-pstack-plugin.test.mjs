import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    PSTACK_MARKETPLACE_REPOSITORY,
    PSTACK_PLUGIN_HOSTS,
    PSTACK_PLUGIN_IDENTIFIER,
    ALL_RETIRED_PLUGIN_SPECS,
    PSTACK_PLUGIN_SPEC,
    SECURITY_GUIDANCE_PLUGIN_SPEC,
    SUBAGENT_MODELS_PLUGIN_SPEC,
    USAGE_WRAPUP_PLUGIN_SPEC,
    hostCommandInvocation,
    installMarketplacePlugins,
    marketplacePluginsPlan,
    removeOrphanedPluginVersions,
    removeStaleMarketplaceClone,
    removeRetiredMarketplacePlugins,
    restartNotice,
    shouldInstallMarketplacePlugin,
} from './install-pstack-plugin.mjs';

function recordingRunner(outcomeForCommand = () => ({ status: 0, stderr: '' })) {
    const calls = [];
    return {
        calls,
        runCommand(executable, commandArguments, options) {
            calls.push({ executable, commandArguments, environment: options.environment });
            return outcomeForCommand(executable, commandArguments);
        },
    };
}

const ROOTS = Object.freeze({
    claudeRoot: '/managed/.claude',
    codexHome: '/managed/.codex',
    environment: {},
});

const WINDOWS_ENVIRONMENT = Object.freeze({ ComSpec: 'C:\\Windows\\system32\\cmd.exe' });

test('the Claude plan carries the two documented plugin commands', () => {
    const plan = marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'claude');
    assert.equal(plan.executable, 'claude');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
    ]);
});

test('the Codex plan adds the plugin with the Codex verb', () => {
    const plan = marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'codex');
    assert.equal(plan.executable, 'codex');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'add', PSTACK_PLUGIN_IDENTIFIER],
    ]);
});

test('an unsupported host names the hosts this installer knows', () => {
    assert.throws(() => marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'cursor'), /cursor/);
    assert.deepEqual(PSTACK_PLUGIN_HOSTS, ['claude', 'codex']);
});

test('each host installs into the managed root this run wrote', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['claude', 'plugin', 'marketplace', 'update', 'pstack-claude'],
        ['claude', 'plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
        ['claude', 'plugin', 'update', PSTACK_PLUGIN_IDENTIFIER],
        ['codex', 'plugin', 'remove', PSTACK_PLUGIN_IDENTIFIER],
        ['codex', 'plugin', 'marketplace', 'remove', 'pstack-claude'],
        ['codex', 'plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['codex', 'plugin', 'add', PSTACK_PLUGIN_IDENTIFIER],
    ]);
    assert.equal(runner.calls[0].environment.CLAUDE_CONFIG_DIR, ROOTS.claudeRoot);
    assert.equal(runner.calls[4].environment.CODEX_HOME, ROOTS.codexHome);
});

test('the Claude plan refreshes in place and Codex has no refresh commands', () => {
    assert.deepEqual(marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'claude').refreshCommands, [
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'marketplace', 'update', 'pstack-claude'],
        ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
        ['plugin', 'update', PSTACK_PLUGIN_IDENTIFIER],
    ]);
    assert.deepEqual(marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'codex').refreshCommands, []);
});

test('a Claude refresh that passes never uninstalls the plugin or removes its marketplace', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'installed');
    const allRemovalCalls = runner.calls.filter(call => (
        call.commandArguments.includes('uninstall') || call.commandArguments.includes('remove')
    ));
    assert.deepEqual(allRemovalCalls, []);
});

test('a failed Claude refresh falls back to removing and adding the marketplace again', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments[2] === 'add' && runner.calls.length === 1
            ? { status: 1, stderr: "its source doesn't match its extraKnownMarketplaces entry" }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.map(call => call.commandArguments), [
        ['plugin', 'marketplace', 'add', 'jl-cmd-projects/claude-dev-env', '--sparse', '.claude-plugin', 'packages/usage-wrapup'],
        ['plugin', 'uninstall', 'usage-wrapup@claude-dev-env'],
        ['plugin', 'marketplace', 'remove', 'claude-dev-env'],
        ['plugin', 'marketplace', 'add', 'jl-cmd-projects/claude-dev-env', '--sparse', '.claude-plugin', 'packages/usage-wrapup'],
        ['plugin', 'install', 'usage-wrapup@claude-dev-env'],
    ]);
});

test('a Claude refresh error printed on standard output still triggers the rebuild', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments[2] === 'add' && runner.calls.length === 1
            ? { status: 1, stdout: "its source doesn't match its extraKnownMarketplaces entry", stderr: '' }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'installed');
    assert.ok(runner.calls.some(call => call.commandArguments.includes('uninstall')));
});

test('a Claude refresh that fails on the network keeps the installed plugin and reports the failure', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments[1] === 'update'
            ? { status: 1, stderr: 'Failed to update plugin: getaddrinfo ENOTFOUND github.com' }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'failed');
    assert.match(outcome.hosts[0].warning, /claude plugin update pstack@pstack-claude failed: .*ENOTFOUND/);
    const allRemovalCalls = runner.calls.filter(call => (
        call.commandArguments.includes('uninstall') || call.commandArguments.includes('remove')
    ));
    assert.deepEqual(allRemovalCalls, []);
});

test('each host removes the installed plugin and marketplace before a clean install', () => {
    assert.deepEqual(marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'claude').removalCommands, [
        ['plugin', 'uninstall', PSTACK_PLUGIN_IDENTIFIER],
        ['plugin', 'marketplace', 'remove', 'pstack-claude'],
    ]);
    assert.deepEqual(marketplacePluginsPlan([PSTACK_PLUGIN_SPEC], 'codex').removalCommands, [
        ['plugin', 'remove', PSTACK_PLUGIN_IDENTIFIER],
        ['plugin', 'marketplace', 'remove', 'pstack-claude'],
    ]);
});

test('a removal that finds nothing installed still lets the install run', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments.includes('uninstall') || commandArguments.includes('remove')
            ? { status: 1, stderr: 'not installed' }
            : commandArguments.includes('update')
                ? { status: 1, stderr: 'Source path does not exist: plugins/pstack' }
                : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.at(-1).commandArguments, ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER]);
});

test('an absent host command skips that host and leaves the other installed', () => {
    const runner = recordingRunner((executable) => (executable === 'codex'
        ? { status: null, error: Object.assign(new Error('spawn codex ENOENT'), { code: 'ENOENT' }) }
        : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.hosts.find(host => host.host === 'claude').status, 'installed');
    const codex = outcome.hosts.find(host => host.host === 'codex');
    assert.equal(codex.status, 'skipped');
    assert.match(codex.warning, /codex/);
    assert.equal(runner.calls.filter(call => call.executable === 'codex').length, 1);
});

test('a failing command reports that host and still installs the next one', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        executable === 'claude' && commandArguments[2] === 'add'
            ? { status: 1, stderr: 'marketplace unreachable' }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'failed');
    const claude = outcome.hosts.find(host => host.host === 'claude');
    assert.equal(claude.status, 'failed');
    assert.match(claude.warning, /marketplace unreachable/);
    assert.equal(outcome.hosts.find(host => host.host === 'codex').status, 'installed');
    assert.deepEqual(runner.calls.filter(call => call.executable === 'claude').at(-1).commandArguments,
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY]);
});

test('should report every line of a multi-line marketplace add error', () => {
    const cloneFailure = [
        'Failed to add marketplace: Fetching the marketplace from GitHub failed on both attempts.'
            + ' HTTPS (https://github.com/jl-cmd/pstack-claude.git): HTTPS clone timed out',
        '',
        'SSH (git@github.com:jl-cmd/pstack-claude.git): git@github.com: Permission denied (publickey).',
        'fatal: Could not read from remote repository.',
        '',
        'Please make sure you have the correct access rights',
        'and the repository exists.',
    ].join('\r\n');
    const runner = recordingRunner((executable, commandArguments) => (
        executable === 'claude' && commandArguments[2] === 'add'
            ? { status: 1, stderr: cloneFailure }
            : { status: 0, stderr: '' }));
    const claude = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, runner)
        .hosts.find(host => host.host === 'claude');
    assert.equal(
        claude.warning,
        `claude plugin marketplace add ${PSTACK_MARKETPLACE_REPOSITORY} failed: `
        + 'Failed to add marketplace: Fetching the marketplace from GitHub failed on both attempts.'
        + ' HTTPS (https://github.com/jl-cmd/pstack-claude.git): HTTPS clone timed out'
        + ' SSH (git@github.com:jl-cmd/pstack-claude.git): git@github.com: Permission denied (publickey).'
        + ' fatal: Could not read from remote repository.'
        + ' Please make sure you have the correct access rights and the repository exists.',
    );
});

test('an executable override replaces the host command for that host only', () => {
    const runner = recordingRunner();
    installMarketplacePlugins(
        [PSTACK_PLUGIN_SPEC],
        { ...ROOTS, environment: { CDE_CODEX_EXECUTABLE: '/opt/codex/bin/codex' } },
        runner,
    );
    assert.deepEqual([...new Set(runner.calls.map(call => call.executable))], [
        'claude',
        '/opt/codex/bin/codex',
    ]);
});

test('the opt-out flag and variable both turn the step off', () => {
    assert.equal(shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, [], {}), true);
    assert.equal(shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, ['--no-pstack'], {}), false);
    assert.equal(shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, [], { CDE_INSTALL_PSTACK: '0' }), false);
    assert.equal(shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, [], { CDE_INSTALL_PSTACK: '1' }), true);
});

test('a selected host list installs only that host', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], { ...ROOTS, hosts: ['codex'] }, runner);
    assert.deepEqual(outcome.hosts.map(host => host.host), ['codex']);
    assert.deepEqual([...new Set(runner.calls.map(call => call.executable))], ['codex']);
});

test('a non-Windows platform launches the host command directly', () => {
    const invocation = hostCommandInvocation('claude', ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER], 'linux');
    assert.deepEqual(invocation, {
        file: 'claude',
        args: ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
        windowsVerbatimArguments: false,
    });
});

test('Windows launches the host command through cmd.exe, which alone can run a .cmd shim', () => {
    const invocation = hostCommandInvocation(
        'claude', ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER], 'win32', WINDOWS_ENVIRONMENT,
    );
    assert.equal(invocation.file, WINDOWS_ENVIRONMENT.ComSpec);
    assert.deepEqual(invocation.args, [
        '/d',
        '/s',
        '/c',
        `""claude" plugin install ${PSTACK_PLUGIN_IDENTIFIER}"`,
    ]);
    assert.equal(invocation.windowsVerbatimArguments, true);
});

test('a Windows executable path holding a space stays one quoted token', () => {
    const invocation = hostCommandInvocation(
        'C:\\Program Files\\nodejs\\claude.cmd',
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        'win32',
        WINDOWS_ENVIRONMENT,
    );
    assert.equal(
        invocation.args.at(-1),
        `""C:\\Program Files\\nodejs\\claude.cmd" plugin marketplace add ${PSTACK_MARKETPLACE_REPOSITORY}"`,
    );
});

test('a Windows environment without ComSpec falls back to the bare shell name', () => {
    const invocation = hostCommandInvocation('claude', ['plugin'], 'win32', {});
    assert.equal(invocation.file, 'cmd.exe');
});

test("cmd.exe's command-not-found exit code reads as an absent host, not a failure", () => {
    const runner = recordingRunner((executable) => (executable === 'codex'
        ? {
            status: 9009,
            stderr: "'codex' is not recognized as an internal or external command,\noperable program or batch file.",
        }
        : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, runner);
    const codex = outcome.hosts.find(host => host.host === 'codex');
    assert.equal(codex.status, 'skipped');
    assert.equal(outcome.status, 'installed');
    assert.equal(runner.calls.filter(call => call.executable === 'codex').length, 1);
});

test('a non-zero exit that is not command-not-found still reads as a failure', () => {
    const runner = recordingRunner(() => ({ status: 9009, stderr: 'the marketplace rejected the catalog' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.hosts[0].status, 'failed');
    assert.match(outcome.hosts[0].warning, /rejected the catalog/);
});

test('the usage-wrapup plan adds this repository marketplace and installs the plugin on Claude', () => {
    const plan = marketplacePluginsPlan([USAGE_WRAPUP_PLUGIN_SPEC], 'claude');
    assert.equal(plan.executable, 'claude');
    assert.equal(plan.homeVariable, 'CLAUDE_CONFIG_DIR');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', 'jl-cmd-projects/claude-dev-env', '--sparse', '.claude-plugin', 'packages/usage-wrapup'],
        ['plugin', 'install', 'usage-wrapup@claude-dev-env'],
    ]);
});

test('usage-wrapup is a Claude-only plugin and refuses a Codex plan', () => {
    assert.deepEqual(USAGE_WRAPUP_PLUGIN_SPEC.hosts, ['claude']);
    assert.throws(() => marketplacePluginsPlan([USAGE_WRAPUP_PLUGIN_SPEC], 'codex'), /usage-wrapup plugin host codex/);
});

test('installing usage-wrapup runs only the Claude commands, inside the managed Claude root', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(outcome.hosts.map(host => host.host), ['claude']);
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'marketplace', 'add', 'jl-cmd-projects/claude-dev-env', '--sparse', '.claude-plugin', 'packages/usage-wrapup'],
        ['claude', 'plugin', 'marketplace', 'update', 'claude-dev-env'],
        ['claude', 'plugin', 'install', 'usage-wrapup@claude-dev-env'],
        ['claude', 'plugin', 'update', 'usage-wrapup@claude-dev-env'],
    ]);
    for (const call of runner.calls) {
        assert.deepEqual(call.environment, { CLAUDE_CONFIG_DIR: ROOTS.claudeRoot });
    }
});

test('an absent claude command skips usage-wrapup and names the plugin in the warning', () => {
    const runner = recordingRunner(() => ({
        status: null,
        error: Object.assign(new Error('spawn claude ENOENT'), { code: 'ENOENT' }),
    }));
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'skipped');
    assert.match(outcome.warning, /usage-wrapup was not installed for claude/);
});

test('the usage-wrapup opt-out flag and variable turn off only usage-wrapup', () => {
    assert.equal(shouldInstallMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, [], {}), true);
    assert.equal(shouldInstallMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, ['--no-usage-wrapup'], {}), false);
    assert.equal(
        shouldInstallMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, [], { CDE_INSTALL_USAGE_WRAPUP: '0' }),
        false,
    );
    assert.equal(shouldInstallMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, ['--no-pstack'], { CDE_INSTALL_PSTACK: '0' }), true);
    assert.equal(
        shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, ['--no-usage-wrapup'], { CDE_INSTALL_USAGE_WRAPUP: '0' }),
        true,
    );
});

for (const [spec, packageFolder] of [
    [USAGE_WRAPUP_PLUGIN_SPEC, './packages/usage-wrapup'],
    [SUBAGENT_MODELS_PLUGIN_SPEC, './packages/subagent-models'],
]) {
    test(`the repository marketplace lists ${spec.name} from its package folder in this repository`, () => {
        const marketplace = JSON.parse(readFileSync(
            new URL('../../../.claude-plugin/marketplace.json', import.meta.url),
            'utf8',
        ));
        const [pluginName, marketplaceName] = spec.pluginIdentifier.split('@');
        assert.equal(marketplace.name, marketplaceName);
        const entry = marketplace.plugins.find(plugin => plugin.name === pluginName);
        assert.ok(entry, `the marketplace lists ${pluginName}`);
        assert.equal(entry.source, packageFolder);
        assert.ok(spec.sparsePaths.includes(packageFolder.slice(2)), `the sparse checkout holds ${packageFolder}`);
    });
}

test('should add and update the shared marketplace once when installing usage-wrapup and subagent-models together', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC, SUBAGENT_MODELS_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(outcome.hosts.map(host => host.host), ['claude']);
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        [
            'claude', 'plugin', 'marketplace', 'add', 'jl-cmd-projects/claude-dev-env',
            '--sparse', '.claude-plugin', 'packages/usage-wrapup', 'packages/subagent-models',
        ],
        ['claude', 'plugin', 'marketplace', 'update', 'claude-dev-env'],
        ['claude', 'plugin', 'install', 'usage-wrapup@claude-dev-env'],
        ['claude', 'plugin', 'install', 'subagent-models@claude-dev-env'],
        ['claude', 'plugin', 'update', 'usage-wrapup@claude-dev-env'],
        ['claude', 'plugin', 'update', 'subagent-models@claude-dev-env'],
    ]);
});

test('the repository marketplace no longer lists a retired plugin', () => {
    const marketplace = JSON.parse(readFileSync(
        new URL('../../../.claude-plugin/marketplace.json', import.meta.url),
        'utf8',
    ));
    const allListedNames = marketplace.plugins.map(plugin => plugin.name);
    for (const eachRetiredSpec of ALL_RETIRED_PLUGIN_SPECS) {
        assert.equal(allListedNames.includes(eachRetiredSpec.name), false, `${eachRetiredSpec.name} is retired`);
    }
    assert.deepEqual(ALL_RETIRED_PLUGIN_SPECS.map(spec => spec.pluginIdentifier), ['deepen-first-prompt@claude-dev-env']);
});

test('a Claude home that holds a retired plugin gets it uninstalled and its orphaned versions deleted', (context) => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'retired-plugin-'));
    context.after(() => rmSync(claudeRoot, { recursive: true, force: true }));
    const versionsDirectory = join(claudeRoot, 'plugins', 'cache', 'claude-dev-env', 'deepen-first-prompt');
    const orphanedVersion = join(versionsDirectory, '0.1.0');
    mkdirSync(orphanedVersion, { recursive: true });
    const runner = recordingRunner(() => {
        writeFileSync(join(orphanedVersion, '.orphaned_at'), '1');
        return { status: 0, stderr: '' };
    });
    const outcome = removeRetiredMarketplacePlugins(ALL_RETIRED_PLUGIN_SPECS, { claudeRoot, environment: {} }, runner);
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'uninstall', 'deepen-first-prompt@claude-dev-env'],
    ]);
    assert.deepEqual(runner.calls[0].environment, { CLAUDE_CONFIG_DIR: claudeRoot });
    assert.deepEqual(outcome.removedIdentifiers, ['deepen-first-prompt@claude-dev-env']);
    assert.equal(existsSync(orphanedVersion), false);
});

test('a Claude home with no retired plugin runs no command', (context) => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'retired-plugin-'));
    context.after(() => rmSync(claudeRoot, { recursive: true, force: true }));
    const runner = recordingRunner();
    const outcome = removeRetiredMarketplacePlugins(ALL_RETIRED_PLUGIN_SPECS, { claudeRoot, environment: {} }, runner);
    assert.deepEqual(runner.calls, []);
    assert.deepEqual(outcome, { removedIdentifiers: [], removedVersionPaths: [], failedRemovals: [] });
});

test('a failed retired plugin uninstall is reported as failed and keeps its cached versions', (context) => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'retired-plugin-'));
    context.after(() => rmSync(claudeRoot, { recursive: true, force: true }));
    const cachedVersion = join(claudeRoot, 'plugins', 'cache', 'claude-dev-env', 'deepen-first-prompt', '0.1.0');
    mkdirSync(cachedVersion, { recursive: true });
    const runner = recordingRunner(() => ({ status: 1, stderr: 'Plugin not found\n' }));
    const outcome = removeRetiredMarketplacePlugins(ALL_RETIRED_PLUGIN_SPECS, { claudeRoot, environment: {} }, runner);
    assert.deepEqual(outcome.removedIdentifiers, []);
    assert.deepEqual(outcome.failedRemovals, [
        { pluginIdentifier: 'deepen-first-prompt@claude-dev-env', detail: 'Plugin not found' },
    ]);
    assert.equal(existsSync(cachedVersion), true);
});

test('should refuse one plan for plugins from two marketplaces', () => {
    assert.throws(
        () => marketplacePluginsPlan([PSTACK_PLUGIN_SPEC, SUBAGENT_MODELS_PLUGIN_SPEC], 'claude'),
        /subagent-models comes from jl-cmd-projects\/claude-dev-env/,
    );
});

test('should turn off only subagent-models with its opt-out flag or variable', () => {
    assert.equal(shouldInstallMarketplacePlugin(SUBAGENT_MODELS_PLUGIN_SPEC, [], {}), true);
    assert.equal(shouldInstallMarketplacePlugin(SUBAGENT_MODELS_PLUGIN_SPEC, ['--no-subagent-models'], {}), false);
    assert.equal(
        shouldInstallMarketplacePlugin(SUBAGENT_MODELS_PLUGIN_SPEC, [], { CDE_INSTALL_SUBAGENT_MODELS: '0' }),
        false,
    );
    assert.equal(
        shouldInstallMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, ['--no-subagent-models'], { CDE_INSTALL_SUBAGENT_MODELS: '0' }),
        true,
    );
});

test('a clean install deletes the orphaned pstack versions and keeps the installed one', () => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'pstack-orphans-'));
    const versionsDirectory = join(claudeRoot, 'plugins', 'cache', 'pstack-claude', 'pstack');
    mkdirSync(join(versionsDirectory, '0.9.55'), { recursive: true });
    writeFileSync(join(versionsDirectory, '0.9.55', '.orphaned_at'), '1');
    mkdirSync(join(versionsDirectory, '0.9.64'), { recursive: true });
    const outcome = installMarketplacePlugins(
        [PSTACK_PLUGIN_SPEC],
        { claudeRoot, hosts: ['claude'], environment: {} },
        recordingRunner(),
    );
    assert.equal(outcome.status, 'installed');
    assert.equal(existsSync(join(versionsDirectory, '0.9.55')), false);
    assert.equal(existsSync(join(versionsDirectory, '0.9.64')), true);
    assert.deepEqual(removeOrphanedPluginVersions(versionsDirectory), []);
});

test('a plugin folder held by another program names the process to close', () => {
    const lockedError = 'Failed to install plugin "pstack@pstack-claude": The installed copy of this plugin version'
        + ' could not be replaced: it is in use by another program (EPERM).';
    const searchedFolders = [];
    const runner = recordingRunner((executable, commandArguments) => (
        executable === 'claude' && commandArguments[1] === 'install'
            ? { status: 1, stderr: lockedError }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, {
        runCommand: runner.runCommand,
        findLockers: folderPath => {
            searchedFolders.push(folderPath);
            return [{ pid: 19056, name: 'Cursor.exe', reason: 'command-line' }];
        },
    });
    const claude = outcome.hosts.find(host => host.host === 'claude');
    assert.equal(claude.status, 'failed');
    assert.deepEqual(searchedFolders, [join('/managed/.claude', 'plugins', 'cache', 'pstack-claude', 'pstack')]);
    assert.match(claude.warning, /Close Cursor\.exe \(PID 19056, was started on a path inside it\)/);
});

test('a failure that is not a held folder runs no locker search', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        executable === 'claude' && commandArguments[2] === 'add'
            ? { status: 1, stderr: 'owner: Invalid input: expected object, received undefined' }
            : { status: 0, stderr: '' }));
    let searched = false;
    installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, {
        runCommand: runner.runCommand,
        findLockers: () => {
            searched = true;
            return [];
        },
    });
    assert.equal(searched, false);
});

test('a held folder that was not searched adds no claim about what holds it', () => {
    const lockedError = 'Failed to install plugin "pstack@pstack-claude": EPERM: operation not permitted';
    const runner = recordingRunner((executable, commandArguments) => (
        executable === 'claude' && commandArguments[1] === 'install'
            ? { status: 1, stderr: lockedError }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, {
        runCommand: runner.runCommand,
        findLockers: () => null,
    });
    const claude = outcome.hosts.find(host => host.host === 'claude');
    assert.equal(claude.status, 'failed');
    assert.match(claude.warning, /EPERM: operation not permitted$/);
    assert.doesNotMatch(claude.warning, /likely holder|Close /);
});

test('should delete a half-made marketplace clone before the shared marketplace add', () => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'cde-stale-clone-'));
    const cloneDirectory = join(claudeRoot, 'plugins', 'marketplaces', 'jl-cmd-projects-claude-dev-env..clone');
    mkdirSync(join(cloneDirectory, '.git'), { recursive: true });
    writeFileSync(join(cloneDirectory, '.git', 'shallow.lock'), '');
    const allCloneStatesAtAdd = [];
    const outcome = installMarketplacePlugins([USAGE_WRAPUP_PLUGIN_SPEC], { claudeRoot, hosts: ['claude'] }, {
        runCommand: (executable, commandArguments) => {
            if (commandArguments[2] === 'add') allCloneStatesAtAdd.push(existsSync(cloneDirectory));
            return { status: 0, stderr: '' };
        },
    });
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(allCloneStatesAtAdd, [false]);
    rmSync(claudeRoot, { recursive: true, force: true });
});

test('should report no removal when no stale marketplace clone exists', () => {
    assert.equal(removeStaleMarketplaceClone(join(tmpdir(), 'cde-no-such-clone')), false);
});

test('an install prints one restart notice that names each plugin and host', () => {
    const allLoggedLines = [];
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, {
        ...recordingRunner(),
        writeLine: line => allLoggedLines.push(line),
    });
    assert.deepEqual(allLoggedLines, [restartNotice([PSTACK_PLUGIN_SPEC], ['claude', 'codex'])]);
    assert.equal(outcome.restartNotice, allLoggedLines[0]);
    assert.match(allLoggedLines[0], /Restart each open claude and codex session to load Pstack\./);
});

test('a run that installs nothing prints no restart notice', () => {
    const allLoggedLines = [];
    const outcome = installMarketplacePlugins([PSTACK_PLUGIN_SPEC], ROOTS, {
        ...recordingRunner(() => ({ status: null, error: Object.assign(new Error('spawn ENOENT'), { code: 'ENOENT' }) })),
        writeLine: line => allLoggedLines.push(line),
    });
    assert.equal(outcome.status, 'skipped');
    assert.deepEqual(allLoggedLines, []);
    assert.equal(outcome.restartNotice, null);
});
test('should install security-guidance from the official marketplace on Claude only', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugins([SECURITY_GUIDANCE_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(outcome.hosts.map(host => host.host), ['claude']);
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'marketplace', 'add', 'anthropics/claude-plugins-official'],
        ['claude', 'plugin', 'marketplace', 'update', 'claude-plugins-official'],
        ['claude', 'plugin', 'install', 'security-guidance@claude-plugins-official'],
        ['claude', 'plugin', 'update', 'security-guidance@claude-plugins-official'],
    ]);
    assert.equal(runner.calls[0].environment.CLAUDE_CONFIG_DIR, ROOTS.claudeRoot);
});

test('should install against an official marketplace already known under another source', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments[2] === 'add'
            ? { status: 1, stderr: "its source doesn't match its extraKnownMarketplaces entry" }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([SECURITY_GUIDANCE_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.map(call => call.commandArguments), [
        ['plugin', 'marketplace', 'add', 'anthropics/claude-plugins-official'],
        ['plugin', 'marketplace', 'update', 'claude-plugins-official'],
        ['plugin', 'install', 'security-guidance@claude-plugins-official'],
        ['plugin', 'update', 'security-guidance@claude-plugins-official'],
    ]);
});

test('should leave the shared official marketplace in place when its refresh needs a rebuild', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments[1] === 'install'
            ? { status: 1, stderr: 'Source path does not exist: plugins/security-guidance' }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugins([SECURITY_GUIDANCE_PLUGIN_SPEC], ROOTS, runner);
    assert.equal(outcome.status, 'failed');
    assert.match(outcome.warning, /Source path does not exist/);
    assert.equal(
        runner.calls.some(call => call.commandArguments.includes('remove') || call.commandArguments.includes('uninstall')),
        false,
    );
});

test('should turn off only security-guidance with its opt-out flag or variable', () => {
    assert.equal(shouldInstallMarketplacePlugin(SECURITY_GUIDANCE_PLUGIN_SPEC, [], {}), true);
    assert.equal(shouldInstallMarketplacePlugin(SECURITY_GUIDANCE_PLUGIN_SPEC, ['--no-security-guidance'], {}), false);
    assert.equal(
        shouldInstallMarketplacePlugin(SECURITY_GUIDANCE_PLUGIN_SPEC, [], { CDE_INSTALL_SECURITY_GUIDANCE: '0' }),
        false,
    );
    assert.equal(
        shouldInstallMarketplacePlugin(PSTACK_PLUGIN_SPEC, ['--no-security-guidance'], { CDE_INSTALL_SECURITY_GUIDANCE: '0' }),
        true,
    );
});
