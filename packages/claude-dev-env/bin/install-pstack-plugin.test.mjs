import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    PSTACK_MARKETPLACE_REPOSITORY,
    PSTACK_PLUGIN_HOSTS,
    PSTACK_PLUGIN_IDENTIFIER,
    PSTACK_PLUGIN_SPEC,
    USAGE_WRAPUP_PLUGIN_SPEC,
    hostCommandInvocation,
    installMarketplacePlugin,
    marketplacePluginPlan,
    removeOrphanedPluginVersions,
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
    const plan = marketplacePluginPlan(PSTACK_PLUGIN_SPEC, 'claude');
    assert.equal(plan.executable, 'claude');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
    ]);
});

test('the Codex plan adds the plugin with the Codex verb', () => {
    const plan = marketplacePluginPlan(PSTACK_PLUGIN_SPEC, 'codex');
    assert.equal(plan.executable, 'codex');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['plugin', 'add', PSTACK_PLUGIN_IDENTIFIER],
    ]);
});

test('an unsupported host names the hosts this installer knows', () => {
    assert.throws(() => marketplacePluginPlan(PSTACK_PLUGIN_SPEC, 'cursor'), /cursor/);
    assert.deepEqual(PSTACK_PLUGIN_HOSTS, ['claude', 'codex']);
});

test('each host installs into the managed root this run wrote', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'uninstall', PSTACK_PLUGIN_IDENTIFIER],
        ['claude', 'plugin', 'marketplace', 'remove', 'pstack-claude'],
        ['claude', 'plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['claude', 'plugin', 'install', PSTACK_PLUGIN_IDENTIFIER],
        ['codex', 'plugin', 'remove', PSTACK_PLUGIN_IDENTIFIER],
        ['codex', 'plugin', 'marketplace', 'remove', 'pstack-claude'],
        ['codex', 'plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY],
        ['codex', 'plugin', 'add', PSTACK_PLUGIN_IDENTIFIER],
    ]);
    assert.equal(runner.calls[0].environment.CLAUDE_CONFIG_DIR, ROOTS.claudeRoot);
    assert.equal(runner.calls[4].environment.CODEX_HOME, ROOTS.codexHome);
});

test('each host removes the installed plugin and marketplace before it installs', () => {
    assert.deepEqual(marketplacePluginPlan(PSTACK_PLUGIN_SPEC, 'claude').removalCommands, [
        ['plugin', 'uninstall', PSTACK_PLUGIN_IDENTIFIER],
        ['plugin', 'marketplace', 'remove', 'pstack-claude'],
    ]);
    assert.deepEqual(marketplacePluginPlan(PSTACK_PLUGIN_SPEC, 'codex').removalCommands, [
        ['plugin', 'remove', PSTACK_PLUGIN_IDENTIFIER],
        ['plugin', 'marketplace', 'remove', 'pstack-claude'],
    ]);
});

test('a removal that finds nothing installed still lets the install run', () => {
    const runner = recordingRunner((executable, commandArguments) => (
        commandArguments.includes('uninstall') || commandArguments.includes('remove')
            ? { status: 1, stderr: 'not installed' }
            : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(runner.calls.at(-1).commandArguments, ['plugin', 'install', PSTACK_PLUGIN_IDENTIFIER]);
});

test('an absent host command skips that host and leaves the other installed', () => {
    const runner = recordingRunner((executable) => (executable === 'codex'
        ? { status: null, error: Object.assign(new Error('spawn codex ENOENT'), { code: 'ENOENT' }) }
        : { status: 0, stderr: '' }));
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, ROOTS, runner);
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
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, ROOTS, runner);
    assert.equal(outcome.status, 'failed');
    const claude = outcome.hosts.find(host => host.host === 'claude');
    assert.equal(claude.status, 'failed');
    assert.match(claude.warning, /marketplace unreachable/);
    assert.equal(outcome.hosts.find(host => host.host === 'codex').status, 'installed');
    assert.deepEqual(runner.calls.filter(call => call.executable === 'claude').at(-1).commandArguments,
        ['plugin', 'marketplace', 'add', PSTACK_MARKETPLACE_REPOSITORY]);
});

test('an executable override replaces the host command for that host only', () => {
    const runner = recordingRunner();
    installMarketplacePlugin(
        PSTACK_PLUGIN_SPEC,
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
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, { ...ROOTS, hosts: ['codex'] }, runner);
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
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, ROOTS, runner);
    const codex = outcome.hosts.find(host => host.host === 'codex');
    assert.equal(codex.status, 'skipped');
    assert.equal(outcome.status, 'installed');
    assert.equal(runner.calls.filter(call => call.executable === 'codex').length, 1);
});

test('a non-zero exit that is not command-not-found still reads as a failure', () => {
    const runner = recordingRunner(() => ({ status: 9009, stderr: 'the marketplace rejected the catalog' }));
    const outcome = installMarketplacePlugin(PSTACK_PLUGIN_SPEC, { ...ROOTS, hosts: ['claude'] }, runner);
    assert.equal(outcome.hosts[0].status, 'failed');
    assert.match(outcome.hosts[0].warning, /rejected the catalog/);
});

const USAGE_WRAPUP_PINNED_COMMIT = 'd78c314e5787786e866bf5c4967107365854dc78';

test('the usage-wrapup plan adds this repository marketplace and installs the plugin on Claude', () => {
    const plan = marketplacePluginPlan(USAGE_WRAPUP_PLUGIN_SPEC, 'claude');
    assert.equal(plan.executable, 'claude');
    assert.equal(plan.homeVariable, 'CLAUDE_CONFIG_DIR');
    assert.deepEqual(plan.commands, [
        ['plugin', 'marketplace', 'add', 'jl-cmd/claude-dev-env', '--sparse', '.claude-plugin'],
        ['plugin', 'install', 'usage-wrapup@claude-dev-env'],
    ]);
});

test('usage-wrapup is a Claude-only plugin and refuses a Codex plan', () => {
    assert.deepEqual(USAGE_WRAPUP_PLUGIN_SPEC.hosts, ['claude']);
    assert.throws(() => marketplacePluginPlan(USAGE_WRAPUP_PLUGIN_SPEC, 'codex'), /usage-wrapup plugin host codex/);
});

test('installing usage-wrapup runs only the Claude commands, inside the managed Claude root', () => {
    const runner = recordingRunner();
    const outcome = installMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, ROOTS, runner);
    assert.equal(outcome.status, 'installed');
    assert.deepEqual(outcome.hosts.map(host => host.host), ['claude']);
    assert.deepEqual(runner.calls.map(call => [call.executable, ...call.commandArguments]), [
        ['claude', 'plugin', 'uninstall', 'usage-wrapup@claude-dev-env'],
        ['claude', 'plugin', 'marketplace', 'remove', 'claude-dev-env'],
        ['claude', 'plugin', 'marketplace', 'add', 'jl-cmd/claude-dev-env', '--sparse', '.claude-plugin'],
        ['claude', 'plugin', 'install', 'usage-wrapup@claude-dev-env'],
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
    const outcome = installMarketplacePlugin(USAGE_WRAPUP_PLUGIN_SPEC, ROOTS, runner);
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

test('the repository marketplace lists usage-wrapup from the fork, pinned to the reviewed commit', () => {
    const marketplace = JSON.parse(readFileSync(
        new URL('../../../.claude-plugin/marketplace.json', import.meta.url),
        'utf8',
    ));
    const [pluginName, marketplaceName] = USAGE_WRAPUP_PLUGIN_SPEC.pluginIdentifier.split('@');
    assert.equal(marketplace.name, marketplaceName);
    const entry = marketplace.plugins.find(plugin => plugin.name === pluginName);
    assert.ok(entry, `the marketplace lists ${pluginName}`);
    assert.deepEqual(entry.source, {
        source: 'github',
        repo: 'jl-cmd/usage-wrapup',
        ref: 'main',
        sha: USAGE_WRAPUP_PINNED_COMMIT,
    });
});

test('a clean install deletes the orphaned pstack versions and keeps the installed one', () => {
    const claudeRoot = mkdtempSync(join(tmpdir(), 'pstack-orphans-'));
    const versionsDirectory = join(claudeRoot, 'plugins', 'cache', 'pstack-claude', 'pstack');
    mkdirSync(join(versionsDirectory, '0.9.55'), { recursive: true });
    writeFileSync(join(versionsDirectory, '0.9.55', '.orphaned_at'), '1');
    mkdirSync(join(versionsDirectory, '0.9.64'), { recursive: true });
    const outcome = installMarketplacePlugin(
        PSTACK_PLUGIN_SPEC,
        { claudeRoot, hosts: ['claude'], environment: {} },
        recordingRunner(),
    );
    assert.equal(outcome.status, 'installed');
    assert.equal(existsSync(join(versionsDirectory, '0.9.55')), false);
    assert.equal(existsSync(join(versionsDirectory, '0.9.64')), true);
    assert.deepEqual(removeOrphanedPluginVersions(versionsDirectory), []);
});
