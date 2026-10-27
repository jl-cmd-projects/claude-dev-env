import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { findFolderLockers, lockedFolderAdvice, namesALockedFolder } from './folder-lockers.mjs';

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
    sparsePaths: Object.freeze([]),
    pluginIdentifier: PSTACK_PLUGIN_IDENTIFIER,
    hosts: PSTACK_PLUGIN_HOSTS,
    optOutFlag: PSTACK_PLUGIN_OPT_OUT_FLAG,
    optOutVariable: PSTACK_PLUGIN_OPT_OUT_VARIABLE,
});

export const USAGE_WRAPUP_PLUGIN_SPEC = Object.freeze({
    name: 'usage-wrapup',
    label: 'Usage-wrapup',
    marketplaceRepository: 'jl-cmd-projects/claude-dev-env',
    marketplaceName: 'claude-dev-env',
    sparsePaths: Object.freeze(['.claude-plugin', 'packages/usage-wrapup']),
    pluginIdentifier: 'usage-wrapup@claude-dev-env',
    hosts: Object.freeze(['claude']),
    optOutFlag: '--no-usage-wrapup',
    optOutVariable: 'CDE_INSTALL_USAGE_WRAPUP',
});

/**
 * Plugins this installer used to install and now removes from each Claude home
 * that still holds them, so an update leaves none behind.
 */
export const ALL_RETIRED_PLUGIN_SPECS = Object.freeze([
    Object.freeze({
        name: 'deepen-first-prompt',
        marketplaceName: 'claude-dev-env',
        pluginIdentifier: 'deepen-first-prompt@claude-dev-env',
    }),
]);

export const SUBAGENT_MODELS_PLUGIN_SPEC = Object.freeze({
    name: 'subagent-models',
    label: 'Subagent-models',
    marketplaceRepository: 'jl-cmd-projects/claude-dev-env',
    marketplaceName: 'claude-dev-env',
    sparsePaths: Object.freeze(['.claude-plugin', 'packages/subagent-models']),
    pluginIdentifier: 'subagent-models@claude-dev-env',
    hosts: Object.freeze(['claude']),
    optOutFlag: '--no-subagent-models',
    optOutVariable: 'CDE_INSTALL_SUBAGENT_MODELS',
});

/**
 * Anthropic's security-guidance plugin, which reviews each edit, turn, and
 * commit an agent makes for security problems.
 *
 * Its marketplace holds every official Anthropic plugin and may supply other
 * plugins the user installed, so the install never removes that marketplace
 * to rebuild it.
 */
export const SECURITY_GUIDANCE_PLUGIN_SPEC = Object.freeze({
    name: 'security-guidance',
    label: 'Security-guidance',
    marketplaceRepository: 'anthropics/claude-plugins-official',
    marketplaceName: 'claude-plugins-official',
    sparsePaths: Object.freeze([]),
    pluginIdentifier: 'security-guidance@claude-plugins-official',
    hosts: Object.freeze(['claude']),
    optOutFlag: '--no-security-guidance',
    optOutVariable: 'CDE_INSTALL_SECURITY_GUIDANCE',
    sharesMarketplace: true,
});

const HOST_DEFINITIONS = Object.freeze({
    claude: Object.freeze({
        executable: 'claude',
        executableVariable: 'CDE_CLAUDE_EXECUTABLE',
        homeVariable: 'CLAUDE_CONFIG_DIR',
        orphanedVersionsDirectory: (homeDirectory, spec) => join(
            homeDirectory, 'plugins', 'cache', spec.marketplaceName, spec.name,
        ),
        staleCloneDirectory: (homeDirectory, spec) => join(
            homeDirectory, 'plugins', 'marketplaces', `${spec.marketplaceRepository.replaceAll('/', '-')}..clone`,
        ),
        installVerb: 'install',
        uninstallVerb: 'uninstall',
        updateVerb: 'update',
    }),
    codex: Object.freeze({
        executable: 'codex',
        executableVariable: 'CDE_CODEX_EXECUTABLE',
        homeVariable: 'CODEX_HOME',
        installVerb: 'add',
        uninstallVerb: 'remove',
        updateVerb: null,
    }),
});

/**
 * Read the marketplace and plugin commands one host installs a set of plugins with.
 *
 * Every plugin in the set comes from one marketplace. A host with an update
 * verb gets refresh commands: the marketplace add and plugin install leave an
 * existing entry in place, and the update commands then pull the newest
 * published version over it, so an installed plugin stays installed through
 * the whole run. When a refresh command fails for a reason only a rebuild
 * fixes, or the host has no update verb, the removal commands run and take
 * out each installed plugin, its cached versions, and the marketplace clone,
 * and the install commands that follow fetch the newest published version
 * into an empty slot. Removing a marketplace uninstalls each plugin it
 * supplied, so the plan removes and adds that marketplace once for the whole
 * set.
 *
 * Claude Code and Codex publish a marketplace under different plugin verbs, so
 * the install verb belongs to the host and the marketplace and identifier
 * belong to the plugin spec. A spec whose marketplace is a large repository
 * names its sparse paths, and the one marketplace add checks out every path
 * the set names, so the clone holds only the catalog and those plugin folders
 * and stays clear of Windows path-length limits.
 *
 * @param {ReadonlyArray<typeof PSTACK_PLUGIN_SPEC>} allSpecs The plugins to install, from one marketplace.
 * @param {string} host A host every spec names, `claude` or `codex`.
 * @returns {{executable: string, executableVariable: string, homeVariable: string,
 *   refreshCommands: ReadonlyArray<ReadonlyArray<string>>,
 *   removalCommands: ReadonlyArray<ReadonlyArray<string>>,
 *   commands: ReadonlyArray<ReadonlyArray<string>>}} The host's install plan.
 */
export function marketplacePluginsPlan(allSpecs, host) {
    const hostDefinition = HOST_DEFINITIONS[host];
    for (const eachSpec of allSpecs) {
        if (!hostDefinition || !eachSpec.hosts.includes(host)) {
            throw new Error(
                `Unsupported ${eachSpec.name} plugin host ${host}: this installer knows ${eachSpec.hosts.join(', ')}.`,
            );
        }
    }
    const [firstSpec] = allSpecs;
    const otherMarketplaceSpec = allSpecs.find(
        eachSpec => eachSpec.marketplaceRepository !== firstSpec.marketplaceRepository,
    );
    if (otherMarketplaceSpec) {
        throw new Error(
            `${otherMarketplaceSpec.name} comes from ${otherMarketplaceSpec.marketplaceRepository}, `
            + `and one plan installs from ${firstSpec.marketplaceRepository} only.`,
        );
    }
    const allSparsePaths = [...new Set(allSpecs.flatMap(eachSpec => eachSpec.sparsePaths))];
    const sparseArguments = allSparsePaths.length > 0 ? ['--sparse', ...allSparsePaths] : [];
    const marketplaceAddCommand = ['plugin', 'marketplace', 'add', firstSpec.marketplaceRepository, ...sparseArguments];
    const allPluginInstallCommands = allSpecs.map(
        eachSpec => ['plugin', hostDefinition.installVerb, eachSpec.pluginIdentifier],
    );
    const refreshCommands = hostDefinition.updateVerb
        ? [
            marketplaceAddCommand,
            ['plugin', 'marketplace', hostDefinition.updateVerb, firstSpec.marketplaceName],
            ...allPluginInstallCommands,
            ...allSpecs.map(eachSpec => ['plugin', hostDefinition.updateVerb, eachSpec.pluginIdentifier]),
        ]
        : [];
    return {
        executable: hostDefinition.executable,
        executableVariable: hostDefinition.executableVariable,
        homeVariable: hostDefinition.homeVariable,
        refreshCommands,
        removalCommands: [
            ...allSpecs.map(eachSpec => ['plugin', hostDefinition.uninstallVerb, eachSpec.pluginIdentifier]),
            ['plugin', 'marketplace', 'remove', firstSpec.marketplaceName],
        ],
        commands: [marketplaceAddCommand, ...allPluginInstallCommands],
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

const BARE_COMMAND_NAME_PATTERN = /^[A-Za-z0-9_][\w.-]*$/;

/**
 * Build the process launch one platform needs to run a host command.
 *
 * The hosts, `claude`, `codex` and the `npm` that installs Pele, ship on
 * Windows as a `.cmd` shim. Node's synchronous spawn rejects a batch file with
 * `EINVAL` unless a shell runs it, so Windows goes through `cmd.exe /d /s /c`
 * with the whole command line as one verbatim argument. A path carries its own quotes inside that line, which is why the
 * line is passed verbatim rather than quoted again by Node. A bare name stays
 * unquoted because `cmd.exe` hands a quoted bare name to a shim as `%0`, and the
 * shim then resolves `%~dp0` against the working directory instead of its own
 * folder. Every other platform launches the executable directly.
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
    const launchedExecutable = BARE_COMMAND_NAME_PATTERN.test(executable) ? executable : `"${executable}"`;
    const commandLine = [launchedExecutable, ...commandArguments].join(' ');
    return {
        file: environment.ComSpec || 'cmd.exe',
        args: ['/d', '/s', '/c', `"${commandLine}"`],
        windowsVerbatimArguments: true,
    };
}

export function runHostCommand(executable, commandArguments, options = {}) {
    const invocation = hostCommandInvocation(executable, commandArguments);
    const spawned = spawnSync(invocation.file, invocation.args, {
        encoding: 'utf8',
        env: { ...process.env, ...options.environment },
        cwd: options.cwd,
        timeout: options.timeoutMilliseconds,
        windowsVerbatimArguments: invocation.windowsVerbatimArguments,
    });
    return {
        status: spawned.status,
        stdout: spawned.stdout ?? '',
        stderr: spawned.stderr ?? '',
        error: spawned.error,
    };
}

const COMMAND_NOT_FOUND_EXIT_CODE = 9009;
const COMMAND_NOT_FOUND_PATTERN = /is not recognized as an internal or external command/;

export function namesAnAbsentCommand(outcome) {
    if (outcome.error?.code === 'ENOENT') return true;
    return outcome.status === COMMAND_NOT_FOUND_EXIT_CODE
        && COMMAND_NOT_FOUND_PATTERN.test(outcome.stderr ?? '');
}

export function singleLineDetail(text) {
    return (text ?? '').split(/\r?\n/).map(eachLine => eachLine.trim()).filter(Boolean).join(' ');
}

/**
 * Delete the clone folder an interrupted marketplace add left behind.
 *
 * Claude Code clones a marketplace into `<owner>-<repository>..clone` and
 * renames it when the clone finishes. A clone that stops partway leaves that
 * folder with its `.git/shallow.lock`, and `marketplace remove` does not
 * delete it, so every later add fails on the lock. Removing the folder
 * before the add lets the add start from an empty slot.
 *
 * @param {string|undefined} cloneDirectory The leftover clone folder.
 * @returns {boolean} True when a folder was removed.
 */
export function removeStaleMarketplaceClone(cloneDirectory) {
    if (!cloneDirectory || !existsSync(cloneDirectory)) return false;
    rmSync(cloneDirectory, { recursive: true, force: true, maxRetries: 3 });
    return true;
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

function absentHostOutcome(allSpecs, host, executable) {
    const pluginNames = allSpecs.map(eachSpec => eachSpec.name).join(', ');
    return {
        host,
        executable,
        status: 'skipped',
        warning: `${executable} is not on PATH, so ${pluginNames} was not installed for ${host}.`,
    };
}

function lockedFolderDetail(allSpecs, host, homeDirectory, errorText, findLockers) {
    const hostDefinition = HOST_DEFINITIONS[host];
    if (!namesALockedFolder(errorText) || !hostDefinition.orphanedVersionsDirectory || !homeDirectory) return '';
    return allSpecs.map(eachSpec => {
        const pluginCacheDirectory = hostDefinition.orphanedVersionsDirectory(homeDirectory, eachSpec);
        const allLockers = findLockers(pluginCacheDirectory);
        return allLockers === null ? '' : ` ${lockedFolderAdvice(pluginCacheDirectory, allLockers)}`;
    }).join('');
}

const MARKETPLACE_SOURCE_MISMATCH_PATTERN = /doesn't match its extraKnownMarketplaces entry/;
const REBUILD_REQUIRED_PATTERN = new RegExp(`${MARKETPLACE_SOURCE_MISMATCH_PATTERN.source}|Source path does not exist`);

function commandFailureDetail(outcome) {
    return singleLineDetail(outcome.stderr) || singleLineDetail(outcome.stdout)
        || outcome.error?.message || `exit ${outcome.status}`;
}

function failedCommandOutcome(allSpecs, host, homeDirectory, executable, commandArguments, outcome, findLockers) {
    const detail = commandFailureDetail(outcome);
    const lockAdvice = lockedFolderDetail(allSpecs, host, homeDirectory, detail, findLockers);
    return {
        host,
        executable,
        status: 'failed',
        warning: `${executable} ${commandArguments.join(' ')} failed: ${detail}${lockAdvice}`,
    };
}

function refreshInPlace(plan, executable, commandEnvironment, runCommand) {
    for (const commandArguments of plan.refreshCommands) {
        const outcome = runCommand(executable, [...commandArguments], {
            environment: commandEnvironment,
        });
        if (namesAnAbsentCommand(outcome)) return { state: 'absent' };
        if (outcome.status !== 0 || outcome.error) return { state: 'failed', commandArguments, outcome };
    }
    return { state: 'refreshed' };
}

function removeOrphanedVersionsForHost(allSpecs, host, homeDirectory) {
    const hostDefinition = HOST_DEFINITIONS[host];
    if (!hostDefinition.orphanedVersionsDirectory || !homeDirectory) return;
    for (const eachSpec of allSpecs) {
        removeOrphanedPluginVersions(hostDefinition.orphanedVersionsDirectory(homeDirectory, eachSpec));
    }
}

function installForHost(allSpecs, host, homeDirectory, environment, runCommand, findLockers) {
    const plan = marketplacePluginsPlan(allSpecs, host);
    const executable = environment[plan.executableVariable] || plan.executable;
    const commandEnvironment = { [plan.homeVariable]: homeDirectory };
    const staleCloneDirectory = HOST_DEFINITIONS[host].staleCloneDirectory;
    if (staleCloneDirectory && homeDirectory) {
        removeStaleMarketplaceClone(staleCloneDirectory(homeDirectory, allSpecs[0]));
    }
    if (plan.refreshCommands.length > 0) {
        const refreshOutcome = refreshInPlace(plan, executable, commandEnvironment, runCommand);
        if (refreshOutcome.state === 'absent') return absentHostOutcome(allSpecs, host, executable);
        if (refreshOutcome.state === 'refreshed') {
            removeOrphanedVersionsForHost(allSpecs, host, homeDirectory);
            return { host, executable, status: 'installed', warning: null };
        }
        const refreshOutput = `${refreshOutcome.outcome.stderr ?? ''}\n${refreshOutcome.outcome.stdout ?? ''}`;
        const marketplaceIsShared = allSpecs.some(eachSpec => eachSpec.sharesMarketplace);
        const sourceMismatchOnAdd = refreshOutcome.commandArguments === plan.refreshCommands[0]
            && MARKETPLACE_SOURCE_MISMATCH_PATTERN.test(refreshOutput);
        if (marketplaceIsShared && sourceMismatchOnAdd) {
            const knownMarketplacePlan = { ...plan, refreshCommands: plan.refreshCommands.slice(1) };
            const knownMarketplaceOutcome = refreshInPlace(
                knownMarketplacePlan, executable, commandEnvironment, runCommand,
            );
            if (knownMarketplaceOutcome.state === 'refreshed') {
                removeOrphanedVersionsForHost(allSpecs, host, homeDirectory);
                return { host, executable, status: 'installed', warning: null };
            }
            if (knownMarketplaceOutcome.state === 'absent') return absentHostOutcome(allSpecs, host, executable);
            return failedCommandOutcome(
                allSpecs, host, homeDirectory, executable,
                knownMarketplaceOutcome.commandArguments, knownMarketplaceOutcome.outcome, findLockers,
            );
        }
        if (marketplaceIsShared || !REBUILD_REQUIRED_PATTERN.test(refreshOutput)) {
            return failedCommandOutcome(
                allSpecs, host, homeDirectory, executable,
                refreshOutcome.commandArguments, refreshOutcome.outcome, findLockers,
            );
        }
    }
    for (const commandArguments of plan.removalCommands) {
        const outcome = runCommand(executable, [...commandArguments], {
            environment: commandEnvironment,
        });
        if (namesAnAbsentCommand(outcome)) return absentHostOutcome(allSpecs, host, executable);
    }
    if (staleCloneDirectory && homeDirectory) {
        removeStaleMarketplaceClone(staleCloneDirectory(homeDirectory, allSpecs[0]));
    }
    for (const commandArguments of plan.commands) {
        const outcome = runCommand(executable, [...commandArguments], {
            environment: commandEnvironment,
        });
        if (namesAnAbsentCommand(outcome)) return absentHostOutcome(allSpecs, host, executable);
        if (outcome.status !== 0 || outcome.error) {
            return failedCommandOutcome(
                allSpecs, host, homeDirectory, executable, commandArguments, outcome, findLockers,
            );
        }
    }
    removeOrphanedVersionsForHost(allSpecs, host, homeDirectory);
    return { host, executable, status: 'installed', warning: null };
}

/**
 * Build the notice that tells the user to restart each session the install reached.
 *
 * A running Claude Code or Codex session keeps the plugin files it loaded at
 * start, so a plugin installed or updated under it stays unavailable there
 * until the session restarts.
 *
 * @param {ReadonlyArray<typeof PSTACK_PLUGIN_SPEC>} allSpecs The plugins the install wrote.
 * @param {ReadonlyArray<string>} allInstalledHosts The hosts the install reached.
 * @returns {string} The restart notice.
 */
export function restartNotice(allSpecs, allInstalledHosts) {
    const pluginLabels = allSpecs.map(eachSpec => eachSpec.label).join(', ');
    return `Restart each open ${allInstalledHosts.join(' and ')} session to load ${pluginLabels}. `
        + 'A running session keeps the plugin version it loaded at start.';
}

/**
 * Install a set of plugins from one marketplace into each host's own home.
 *
 * Claude Code refreshes in place: it adds the marketplace and installs each
 * plugin, both of which leave an existing entry alone, then updates the
 * marketplace and each plugin. An installed plugin stays installed and enabled
 * through the run, so a session that starts mid-run still loads it, and a
 * failed refresh command reports the host failed and leaves the prior version
 * in place. Two refresh errors need a rebuild: a source that no longer
 * matches the settings entry, and a source path the sparse clone lacks. The
 * host reads either from the failing refresh command's output, then falls
 * back to the clean install Codex always runs: it removes every plugin in the
 * set and then the marketplace, so an older version never survives beside the
 * new one, and adds them again. A removal that finds nothing to remove exits
 * non-zero on a fresh home, and the install goes on. A spec that marks its
 * marketplace as shared skips the rebuild, because removing that marketplace
 * would uninstall plugins this run does not own. When the shared marketplace
 * is already known under another source, the add fails on the mismatch and
 * the host runs the rest of the refresh against the known entry; any other
 * refresh failure reports the host failed.
 * Before each Claude marketplace add, the install deletes the half-made clone
 * folder an interrupted earlier add left, so the add starts in an empty slot.
 *
 * Each host is one member of the batch. A host without its command-line tool
 * is skipped and a host whose command fails is reported, so the rules, hooks,
 * and skills this run already wrote still reach their durable places. An
 * absent tool arrives as a spawn `ENOENT` on other platforms and as
 * `cmd.exe`'s command-not-found exit code on Windows, and both read as
 * skipped. When a host cannot replace a plugin folder because something holds
 * it, the warning names each process that holds it, so the user knows what to
 * close before running the install again. When any host installs, the step
 * prints one restart notice, because an open session keeps the plugin
 * version it loaded at start.
 *
 * @param {ReadonlyArray<typeof PSTACK_PLUGIN_SPEC>} allSpecs The plugins to install, from one marketplace.
 * @param {object} [options] Install targets.
 * @param {string} [options.claudeRoot] The managed Claude root to install into.
 * @param {string} [options.codexHome] The Codex home to install into.
 * @param {string[]} [options.hosts] The hosts to install. Defaults to the hosts every spec names.
 * @param {Record<string, string|undefined>} [options.environment] The process environment.
 * @param {object} [dependencies] Seams for the command runner, the folder locker search, and the line writer.
 * @returns {{status: string, hosts: object[], warning: string|null, restartNotice: string|null}} The outcome per host.
 */
export function installMarketplacePlugins(allSpecs, options = {}, dependencies = {}) {
    const environment = options.environment ?? process.env;
    const runCommand = dependencies.runCommand ?? runHostCommand;
    const findLockers = dependencies.findLockers ?? findFolderLockers;
    const homeDirectories = { claude: options.claudeRoot, codex: options.codexHome };
    const hosts = options.hosts ?? allSpecs[0].hosts.filter(
        eachHost => allSpecs.every(eachSpec => eachSpec.hosts.includes(eachHost)),
    );
    const hostOutcomes = hosts.map(host => installForHost(
        allSpecs,
        host,
        homeDirectories[host],
        environment,
        runCommand,
        findLockers,
    ));
    const failedCount = hostOutcomes.filter(outcome => outcome.status === 'failed').length;
    const installedCount = hostOutcomes.filter(outcome => outcome.status === 'installed').length;
    const status = failedCount > 0 ? 'failed' : (installedCount > 0 ? 'installed' : 'skipped');
    const warnings = hostOutcomes.map(outcome => outcome.warning).filter(Boolean);
    const allInstalledHosts = hostOutcomes
        .filter(outcome => outcome.status === 'installed')
        .map(outcome => outcome.host);
    const notice = allInstalledHosts.length > 0 ? restartNotice(allSpecs, allInstalledHosts) : null;
    if (notice) {
        const writeLine = dependencies.writeLine ?? (line => console.log(line));
        writeLine(notice);
    }
    return { status, hosts: hostOutcomes, warning: warnings.join(' ') || null, restartNotice: notice };
}

/**
 * Uninstall each retired plugin a Claude home still holds.
 *
 * A home holds a retired plugin when its plugin cache has a folder for it. For
 * each such plugin the step runs `claude plugin uninstall` and then deletes
 * the cached versions Claude Code marked as orphaned. A home with no cached
 * folder runs no command, so a fresh install and a second update both leave
 * the home as it stands. A missing `claude` command skips the step. A failed
 * uninstall is recorded in `failedRemovals` with its detail, and its cached
 * versions stay on disk.
 *
 * @param {ReadonlyArray<{name: string, marketplaceName: string, pluginIdentifier: string}>} allRetiredSpecs The retired plugins.
 * @param {object} options Removal targets.
 * @param {string|undefined} options.claudeRoot The managed Claude root.
 * @param {Record<string, string|undefined>} [options.environment] The process environment.
 * @param {object} [dependencies] Seams for the command runner.
 * @returns {{removedIdentifiers: string[], removedVersionPaths: string[], failedRemovals: Array<{pluginIdentifier: string, detail: string}>}} What the step removed and what it could not.
 */
export function removeRetiredMarketplacePlugins(allRetiredSpecs, options, dependencies = {}) {
    const environment = options.environment ?? process.env;
    const runCommand = dependencies.runCommand ?? runHostCommand;
    const hostDefinition = HOST_DEFINITIONS.claude;
    const executable = environment[hostDefinition.executableVariable] || hostDefinition.executable;
    const removedIdentifiers = [];
    const removedVersionPaths = [];
    const failedRemovals = [];
    if (!options.claudeRoot) return { removedIdentifiers, removedVersionPaths, failedRemovals };
    for (const eachSpec of allRetiredSpecs) {
        const versionsDirectory = hostDefinition.orphanedVersionsDirectory(options.claudeRoot, eachSpec);
        if (!existsSync(versionsDirectory)) continue;
        const outcome = runCommand(
            executable,
            ['plugin', hostDefinition.uninstallVerb, eachSpec.pluginIdentifier],
            { environment: { [hostDefinition.homeVariable]: options.claudeRoot } },
        );
        if (namesAnAbsentCommand(outcome)) break;
        if (outcome.status !== 0 || outcome.error) {
            const detail = commandFailureDetail(outcome);
            failedRemovals.push({ pluginIdentifier: eachSpec.pluginIdentifier, detail });
            continue;
        }
        removedIdentifiers.push(eachSpec.pluginIdentifier);
        removedVersionPaths.push(...removeOrphanedPluginVersions(versionsDirectory));
    }
    return { removedIdentifiers, removedVersionPaths, failedRemovals };
}
