import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';

export const PSTACK_MARKETPLACE_REPOSITORY = 'jl-cmd/pstack-claude';
export const PSTACK_MARKETPLACE_NAME = 'pstack-claude';
export const PSTACK_PLUGIN_IDENTIFIER = `pstack@${PSTACK_MARKETPLACE_NAME}`;
export const PSTACK_PLUGIN_HOSTS = Object.freeze(['claude', 'codex']);

export const PSTACK_PLUGIN_OPT_OUT_FLAG = '--no-pstack';
export const PSTACK_PLUGIN_OPT_OUT_VARIABLE = 'CDE_INSTALL_PSTACK';

export const PSTACK_PLUGIN_SPEC = Object.freeze({
    name: 'pstack',
    label: 'Pstack',
    marketplaceRepository: PSTACK_MARKETPLACE_REPOSITORY,
    marketplaceName: PSTACK_MARKETPLACE_NAME,
    marketplaceAddArguments: Object.freeze([]),
    pluginIdentifier: PSTACK_PLUGIN_IDENTIFIER,
    hosts: PSTACK_PLUGIN_HOSTS,
    optOutFlag: PSTACK_PLUGIN_OPT_OUT_FLAG,
    optOutVariable: PSTACK_PLUGIN_OPT_OUT_VARIABLE,
});

export const USAGE_WRAPUP_PLUGIN_SPEC = Object.freeze({
    name: 'usage-wrapup',
    label: 'Usage-wrapup',
    marketplaceRepository: 'jl-cmd/claude-dev-env',
    marketplaceName: 'claude-dev-env',
    marketplaceAddArguments: Object.freeze(['--sparse', '.claude-plugin']),
    pluginIdentifier: 'usage-wrapup@claude-dev-env',
    hosts: Object.freeze(['claude']),
    optOutFlag: '--no-usage-wrapup',
    optOutVariable: 'CDE_INSTALL_USAGE_WRAPUP',
});

const HOST_DEFINITIONS = Object.freeze({
    claude: Object.freeze({
        executable: 'claude',
        executableVariable: 'CDE_CLAUDE_EXECUTABLE',
        homeVariable: 'CLAUDE_CONFIG_DIR',
        orphanedVersionsDirectory: (homeDirectory, spec) => join(
            homeDirectory, 'plugins', 'cache', spec.marketplaceName, spec.name,
        ),
        installVerb: 'install',
        uninstallVerb: 'uninstall',
    }),
    codex: Object.freeze({
        executable: 'codex',
        executableVariable: 'CDE_CODEX_EXECUTABLE',
        homeVariable: 'CODEX_HOME',
        installVerb: 'add',
        uninstallVerb: 'remove',
    }),
});

/**
 * Read the marketplace and plugin commands one host installs a plugin with.
 *
 * The removal commands run first and take out the installed plugin, its
 * cached versions, and the marketplace clone, so the install commands that
 * follow fetch the newest published version into an empty slot.
 *
 * Claude Code and Codex publish a marketplace under different plugin verbs, so
 * the install verb belongs to the host and the marketplace and identifier
 * belong to the plugin spec. A spec whose marketplace is a large repository
 * passes `--sparse .claude-plugin` among its marketplace add arguments, so the
 * clone holds only the catalog and stays clear of Windows path-length limits.
 *
 * @param {typeof PSTACK_PLUGIN_SPEC} spec The plugin to install.
 * @param {string} host A host the spec names, `claude` or `codex`.
 * @returns {{executable: string, executableVariable: string, homeVariable: string,
 *   removalCommands: ReadonlyArray<ReadonlyArray<string>>,
 *   commands: ReadonlyArray<ReadonlyArray<string>>}} The host's install plan.
 */
export function marketplacePluginPlan(spec, host) {
    const hostDefinition = HOST_DEFINITIONS[host];
    if (!hostDefinition || !spec.hosts.includes(host)) {
        throw new Error(
            `Unsupported ${spec.name} plugin host ${host}: this installer knows ${spec.hosts.join(', ')}.`,
        );
    }
    return {
        executable: hostDefinition.executable,
        executableVariable: hostDefinition.executableVariable,
        homeVariable: hostDefinition.homeVariable,
        removalCommands: [
            ['plugin', hostDefinition.uninstallVerb, spec.pluginIdentifier],
            ['plugin', 'marketplace', 'remove', spec.marketplaceName],
        ],
        commands: [
            ['plugin', 'marketplace', 'add', spec.marketplaceRepository, ...spec.marketplaceAddArguments],
            ['plugin', hostDefinition.installVerb, spec.pluginIdentifier],
        ],
    };
}

/**
 * Decide whether a full install also installs one marketplace plugin.
 *
 * The step reaches the network for the marketplace repository. The spec's
 * opt-out flag on the command line, or its opt-out variable set to `0` in the
 * environment, turns it off for an air-gapped or offline run.
 *
 * @param {typeof PSTACK_PLUGIN_SPEC} spec The plugin to install.
 * @param {string[]} [argumentList] The command-line arguments after the script.
 * @param {Record<string, string|undefined>} [environment] The process environment.
 * @returns {boolean} True when this run installs the plugin.
 */
export function shouldInstallMarketplacePlugin(
    spec,
    argumentList = process.argv.slice(2),
    environment = process.env,
) {
    if (argumentList.includes(spec.optOutFlag)) return false;
    return environment[spec.optOutVariable] !== '0';
}

/**
 * Build the process launch one platform needs to run a host command.
 *
 * Both hosts ship on Windows as a `.cmd` shim, and Node's synchronous spawn
 * rejects a batch file with `EINVAL` unless a shell runs it, so Windows goes
 * through `cmd.exe /d /s /c` with the whole command line as one verbatim
 * argument. The executable carries its own quotes inside that line, which is
 * why the line is passed verbatim rather than quoted again by Node. Every
 * other platform launches the executable directly.
 *
 * @param {string} executable The host command, a bare name or a path.
 * @param {string[]} commandArguments The arguments after the executable.
 * @param {string} [platform] The platform to build for.
 * @param {Record<string, string|undefined>} [environment] Supplies `ComSpec`.
 * @returns {{file: string, args: string[], windowsVerbatimArguments: boolean}} The launch.
 */
export function hostCommandInvocation(
    executable,
    commandArguments,
    platform = process.platform,
    environment = process.env,
) {
    if (platform !== 'win32') {
        return { file: executable, args: [...commandArguments], windowsVerbatimArguments: false };
    }
    const commandLine = [`"${executable}"`, ...commandArguments].join(' ');
    return {
        file: environment.ComSpec || 'cmd.exe',
        args: ['/d', '/s', '/c', `"${commandLine}"`],
        windowsVerbatimArguments: true,
    };
}

function runHostCommand(executable, commandArguments, options) {
    const invocation = hostCommandInvocation(executable, commandArguments);
    const spawned = spawnSync(invocation.file, invocation.args, {
        encoding: 'utf8',
        env: { ...process.env, ...options.environment },
        windowsVerbatimArguments: invocation.windowsVerbatimArguments,
    });
    return { status: spawned.status, stderr: spawned.stderr ?? '', error: spawned.error };
}

const COMMAND_NOT_FOUND_EXIT_CODE = 9009;
const COMMAND_NOT_FOUND_PATTERN = /is not recognized as an internal or external command/;

function namesAnAbsentCommand(outcome) {
    if (outcome.error?.code === 'ENOENT') return true;
    return outcome.status === COMMAND_NOT_FOUND_EXIT_CODE
        && COMMAND_NOT_FOUND_PATTERN.test(outcome.stderr ?? '');
}

function firstLine(text) {
    const trimmed = (text ?? '').trim();
    if (!trimmed) return '';
    return trimmed.split(/\r?\n/).filter(Boolean).at(-1);
}

const ORPHANED_VERSION_MARKER = '.orphaned_at';

/**
 * Delete each cached plugin version the host marked as orphaned.
 *
 * Claude Code keeps an uninstalled version in its plugin cache with an
 * `.orphaned_at` marker, so the clean install deletes those versions and
 * leaves the version it just installed.
 *
 * @param {string|undefined} versionsDirectory The plugin's cache directory.
 * @returns {string[]} The version directories removed.
 */
export function removeOrphanedPluginVersions(versionsDirectory) {
    if (!versionsDirectory || !existsSync(versionsDirectory)) return [];
    const removedPaths = [];
    for (const versionName of readdirSync(versionsDirectory)) {
        const versionPath = join(versionsDirectory, versionName);
        if (!existsSync(join(versionPath, ORPHANED_VERSION_MARKER))) continue;
        rmSync(versionPath, { recursive: true, force: true });
        removedPaths.push(versionPath);
    }
    return removedPaths;
}

function absentHostOutcome(spec, host, executable) {
    return {
        host,
        executable,
        status: 'skipped',
        warning: `${executable} is not on PATH, so ${spec.name} was not installed for ${host}.`,
    };
}

function installForHost(spec, host, homeDirectory, environment, runCommand) {
    const plan = marketplacePluginPlan(spec, host);
    const executable = environment[plan.executableVariable] || plan.executable;
    const commandEnvironment = { [plan.homeVariable]: homeDirectory };
    for (const commandArguments of plan.removalCommands) {
        const outcome = runCommand(executable, [...commandArguments], {
            environment: commandEnvironment,
        });
        if (namesAnAbsentCommand(outcome)) return absentHostOutcome(spec, host, executable);
    }
    for (const commandArguments of plan.commands) {
        const outcome = runCommand(executable, [...commandArguments], {
            environment: commandEnvironment,
        });
        if (namesAnAbsentCommand(outcome)) return absentHostOutcome(spec, host, executable);
        if (outcome.status !== 0 || outcome.error) {
            const detail = firstLine(outcome.stderr) || outcome.error?.message || `exit ${outcome.status}`;
            return {
                host,
                executable,
                status: 'failed',
                warning: `${executable} ${commandArguments.join(' ')} failed: ${detail}`,
            };
        }
    }
    const hostDefinition = HOST_DEFINITIONS[host];
    if (hostDefinition.orphanedVersionsDirectory && homeDirectory) {
        removeOrphanedPluginVersions(hostDefinition.orphanedVersionsDirectory(homeDirectory, spec));
    }
    return { host, executable, status: 'installed', warning: null };
}

/**
 * Install one plugin from its marketplace into each host's own home.
 *
 * Each host first removes the plugin and its marketplace, so an older
 * version never survives beside the new one. A removal that finds nothing
 * to remove exits non-zero on a fresh home, and the install goes on.
 *
 * Each host is one member of the batch. A host without its command-line tool
 * is skipped and a host whose command fails is reported, so the rules, hooks,
 * and skills this run already wrote still reach their durable places. An
 * absent tool arrives as a spawn `ENOENT` on other platforms and as
 * `cmd.exe`'s command-not-found exit code on Windows, and both read as
 * skipped.
 *
 * @param {typeof PSTACK_PLUGIN_SPEC} spec The plugin to install.
 * @param {object} [options] Install targets.
 * @param {string} [options.claudeRoot] The managed Claude root to install into.
 * @param {string} [options.codexHome] The Codex home to install into.
 * @param {string[]} [options.hosts] The hosts to install. Defaults to the spec's hosts.
 * @param {Record<string, string|undefined>} [options.environment] The process environment.
 * @param {object} [dependencies] Seams for the command runner.
 * @returns {{status: string, hosts: object[], warning: string|null}} The outcome per host.
 */
export function installMarketplacePlugin(spec, options = {}, dependencies = {}) {
    const environment = options.environment ?? process.env;
    const runCommand = dependencies.runCommand ?? runHostCommand;
    const homeDirectories = { claude: options.claudeRoot, codex: options.codexHome };
    const hosts = options.hosts ?? spec.hosts;
    const hostOutcomes = hosts.map(host => installForHost(
        spec,
        host,
        homeDirectories[host],
        environment,
        runCommand,
    ));
    const failedCount = hostOutcomes.filter(outcome => outcome.status === 'failed').length;
    const installedCount = hostOutcomes.filter(outcome => outcome.status === 'installed').length;
    const status = failedCount > 0 ? 'failed' : (installedCount > 0 ? 'installed' : 'skipped');
    const warnings = hostOutcomes.map(outcome => outcome.warning).filter(Boolean);
    return { status, hosts: hostOutcomes, warning: warnings.join(' ') || null };
}
