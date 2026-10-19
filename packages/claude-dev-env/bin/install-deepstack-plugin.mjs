import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    installMarketplacePlugins,
    marketplacePluginsPlan,
    shouldInstallMarketplacePlugin,
} from './install-pstack-plugin.mjs';
import {
    CURSOR_BEFORE_SUBMIT_PROMPT_EVENT,
    CURSOR_HOOK_TIMEOUT_SECONDS,
    CURSOR_SESSION_START_EVENT,
} from './install-constants.mjs';
import { updateCursorHooksFile, withOwnedCursorHooks, withoutOwnedCursorHooks } from './cursor-native-hooks.mjs';

export const DEEPSTACK_MARKETPLACE_REPOSITORY = 'jl-cmd-projects/DeepStack';
export const DEEPSTACK_MARKETPLACE_NAME = 'DeepStack';
export const DEEPSTACK_PLUGIN_NAME = 'deepstack';
export const DEEPSTACK_PLUGIN_IDENTIFIER = `${DEEPSTACK_PLUGIN_NAME}@${DEEPSTACK_MARKETPLACE_NAME}`;
export const DEEPSTACK_PLUGIN_HOSTS = Object.freeze(['claude', 'codex']);
export const DEEPSTACK_PLUGIN_OPT_OUT_FLAG = '--no-deepstack';
export const DEEPSTACK_PLUGIN_OPT_OUT_VARIABLE = 'CDE_INSTALL_DEEPSTACK';
export const DEEPSTACK_SOURCE_VARIABLE = 'CDE_DEEPSTACK_SOURCE';
export const DEEPSTACK_CURSOR_DIRECTORY_NAME = 'plugins/deepstack';
/** Name prefix of the temporary DeepStack clone a full install makes when no local tree exists. */
export const DEEPSTACK_CLONE_PREFIX = 'deepstack-';
const CLONE_REMOVAL_RETRIES = 3;
export const DEEPSTACK_SKILL_RELATIVE_PATH = 'skills/deepstack-mode/SKILL.md';
export const DEEPSTACK_SESSION_SCRIPT_RELATIVE_PATH = 'hooks/session-start.sh';
export const DEEPSTACK_SESSION_POWERSHELL_RELATIVE_PATH = 'hooks/session-start.ps1';
export const DEEPSTACK_CURSOR_SESSION_COMMAND_MARKER = 'plugins/deepstack/hooks/session-start.';
export const DEEPSTACK_SESSION_RUNTIME = 'cursor';
const WINDOWS_POWERSHELL_FILE_PREFIX = 'powershell -NoProfile -ExecutionPolicy Bypass -File';
const DEFAULT_PYTHON_COMMAND = 'python3';
export const DEEPSTACK_FIRST_TASK_HOOK_NAME = 'deepen_first_prompt.py';
export const DEEPSTACK_CODEX_MODEL_SHEET_NAME = 'deepstack-models.md';

export const DEEPSTACK_PLUGIN_SPEC = Object.freeze({
    name: DEEPSTACK_PLUGIN_NAME,
    label: 'DeepStack',
    marketplaceRepository: DEEPSTACK_MARKETPLACE_REPOSITORY,
    marketplaceName: DEEPSTACK_MARKETPLACE_NAME,
    sparsePaths: Object.freeze([]),
    pluginIdentifier: DEEPSTACK_PLUGIN_IDENTIFIER,
    hosts: DEEPSTACK_PLUGIN_HOSTS,
    optOutFlag: DEEPSTACK_PLUGIN_OPT_OUT_FLAG,
    optOutVariable: DEEPSTACK_PLUGIN_OPT_OUT_VARIABLE,
});

/**
 * Quote one path for a hook command line.
 *
 * @param {string} pathValue The absolute path.
 * @returns {string} A single-quoted shell word.
 */
function quoteCommandPath(pathValue) {
    return `'${pathValue.replaceAll("'", `'\\''`)}'`;
}

/**
 * Read the Claude, Codex, and Cursor actions one DeepStack install performs.
 *
 * Claude and Codex use the marketplace verbs. Cursor has no plugin command, so
 * its action is a copy into the Cursor home plus two native hook registrations.
 *
 * @returns {{claude: object, codex: object, cursor: {
 *   pluginDirectoryName: string,
 *   skillRelativePath: string,
 *   sessionScriptRelativePath: string,
 *   sessionRuntimeArgument: string,
 *   firstTaskHookName: string,
 * }}} The three host actions.
 */
export function deepStackInstallPlan() {
    return {
        claude: marketplacePluginsPlan([DEEPSTACK_PLUGIN_SPEC], 'claude'),
        codex: marketplacePluginsPlan([DEEPSTACK_PLUGIN_SPEC], 'codex'),
        cursor: {
            pluginDirectoryName: DEEPSTACK_CURSOR_DIRECTORY_NAME,
            skillRelativePath: DEEPSTACK_SKILL_RELATIVE_PATH,
            sessionScriptRelativePath: DEEPSTACK_SESSION_SCRIPT_RELATIVE_PATH,
            sessionRuntimeArgument: DEEPSTACK_SESSION_RUNTIME,
            firstTaskHookName: DEEPSTACK_FIRST_TASK_HOOK_NAME,
        },
    };
}

/**
 * @param {string|undefined} homeDirectory A Claude or Codex home.
 * @returns {string|null} The newest cached plugin directory, or null.
 */
function newestCachedPlugin(homeDirectory) {
    if (!homeDirectory) return null;
    const cacheDirectory = join(
        homeDirectory,
        'plugins',
        'cache',
        DEEPSTACK_MARKETPLACE_NAME,
        DEEPSTACK_PLUGIN_NAME,
    );
    if (!existsSync(cacheDirectory)) return null;
    const versions = readdirSync(cacheDirectory, { withFileTypes: true })
        .filter(entry => entry.isDirectory())
        .map(entry => entry.name)
        .filter(name => existsSync(join(cacheDirectory, name, DEEPSTACK_SKILL_RELATIVE_PATH)))
        .sort();
    if (versions.length === 0) return null;
    return join(cacheDirectory, versions[versions.length - 1]);
}

/**
 * Find the plugin tree to copy into Cursor.
 *
 * An explicit directory wins, then the source variable, then a marketplace
 * cache written by the Claude or Codex install, then a shallow clone of
 * jl-cmd-projects/DeepStack.
 *
 * @param {object} options Search inputs.
 * @param {string} [options.claudeRoot] The Claude home.
 * @param {string} [options.codexHome] The Codex home.
 * @param {Record<string, string|undefined>} [options.environment] The process environment.
 * @param {string} [options.sourceDirectory] A directory that already holds the plugin.
 * @param {(destination: string) => string|null} [options.cloneRepository] Replaces the git clone.
 * @returns {string|null} The plugin directory, or null when every source is empty.
 */
export function resolveDeepStackPluginSource(options = {}) {
    if (options.sourceDirectory && existsSync(join(options.sourceDirectory, DEEPSTACK_SKILL_RELATIVE_PATH))) {
        return options.sourceDirectory;
    }
    const environment = options.environment ?? process.env;
    const fromEnvironment = environment[DEEPSTACK_SOURCE_VARIABLE];
    if (fromEnvironment && existsSync(join(fromEnvironment, DEEPSTACK_SKILL_RELATIVE_PATH))) {
        return fromEnvironment;
    }
    const cached = newestCachedPlugin(options.claudeRoot) ?? newestCachedPlugin(options.codexHome);
    if (cached) return cached;
    if (options.cloneRepository) return options.cloneRepository();
    return null;
}

/**
 * True for a Cursor hook command the DeepStack install owns.
 *
 * @param {string} forwardSlashedCommand A hook command with forward slashes.
 * @returns {boolean} True for the DeepStack session hook or the first-task hook.
 */
export function isDeepStackCursorCommand(forwardSlashedCommand) {
    return forwardSlashedCommand.includes(DEEPSTACK_CURSOR_SESSION_COMMAND_MARKER)
        || forwardSlashedCommand.includes(DEEPSTACK_FIRST_TASK_HOOK_NAME);
}

/**
 * Return the native Cursor configuration with one DeepStack session entry and one first-task entry.
 *
 * Earlier installs wrote these as Claude-style groups, which Cursor never ran;
 * every owned copy, old or new, is replaced by one native entry each.
 *
 * @param {object} configuration The parsed Cursor hooks file.
 * @param {{sessionCommand: string, firstTaskCommand: string}} commands The two commands.
 * @returns {object} The configuration with both native entries present once.
 */
export function mergeDeepStackCursorHooks(configuration, commands) {
    return withOwnedCursorHooks(configuration, isDeepStackCursorCommand, {
        [CURSOR_SESSION_START_EVENT]: [{ command: commands.sessionCommand, timeout: CURSOR_HOOK_TIMEOUT_SECONDS }],
        [CURSOR_BEFORE_SUBMIT_PROMPT_EVENT]: [{ command: commands.firstTaskCommand, timeout: CURSOR_HOOK_TIMEOUT_SECONDS }],
    });
}

/**
 * Remove the DeepStack session and first-task entries from the Cursor hooks file.
 *
 * @param {string} cursorDirectory The Cursor home.
 * @returns {string|null} The hooks.json path when this call changed it.
 */
export function removeDeepStackCursorHooks(cursorDirectory) {
    return updateCursorHooksFile(
        cursorDirectory,
        configuration => withoutOwnedCursorHooks(configuration, isDeepStackCursorCommand),
    );
}

/**
 * Build the Cursor command for the DeepStack session script.
 *
 * Cursor runs hook commands through PowerShell on Windows, where a `.sh` path
 * does not run, so Windows uses the plugin's `session-start.ps1`.
 *
 * @param {string} pluginDirectory The plugin copy in the Cursor home.
 * @param {(pathValue: string) => string} formatPathArgument The platform path quoting.
 * @param {string} platform The Node platform name.
 * @returns {string} The session command.
 */
export function deepStackCursorSessionCommand(pluginDirectory, formatPathArgument, platform) {
    const plan = deepStackInstallPlan().cursor;
    const powerShellScript = join(pluginDirectory, DEEPSTACK_SESSION_POWERSHELL_RELATIVE_PATH);
    if (platform === 'win32' && existsSync(powerShellScript)) {
        return `${WINDOWS_POWERSHELL_FILE_PREFIX} ${formatPathArgument(powerShellScript)} ${plan.sessionRuntimeArgument}`;
    }
    return `${formatPathArgument(join(pluginDirectory, plan.sessionScriptRelativePath))} ${plan.sessionRuntimeArgument}`;
}

/**
 * Copy the plugin into the Cursor home and register both hooks in Cursor's native format.
 *
 * @param {object} options Copy inputs.
 * @param {string} options.cursorDirectory The Cursor home, usually ~/.cursor.
 * @param {string|null} options.pluginSourceDirectory The plugin tree to copy.
 * @param {string} options.firstTaskHookPath Absolute path of deepen_first_prompt.py.
 * @param {string} [options.pythonCommand] The interpreter the installer detected.
 * @param {(pathValue: string) => string} [options.formatPathArgument] The platform path quoting.
 * @param {string} [options.platform] The Node platform name.
 * @returns {{status: string, pluginDirectory: string|null, hooksPath: string|null, warning: string|null}} The outcome.
 */
export function installDeepStackCursor(options) {
    const plan = deepStackInstallPlan().cursor;
    if (!options.cursorDirectory) {
        return { status: 'failed', pluginDirectory: null, hooksPath: null, warning: 'Cursor home is unset.' };
    }
    if (!options.pluginSourceDirectory) {
        return {
            status: 'failed',
            pluginDirectory: null,
            hooksPath: null,
            warning: `No ${DEEPSTACK_MARKETPLACE_REPOSITORY} plugin tree to copy.`,
        };
    }
    const pluginDirectory = join(options.cursorDirectory, plan.pluginDirectoryName);
    mkdirSync(options.cursorDirectory, { recursive: true });
    cpSync(options.pluginSourceDirectory, pluginDirectory, { recursive: true, force: true });
    const formatPathArgument = options.formatPathArgument ?? quoteCommandPath;
    const pythonCommand = options.pythonCommand ?? DEFAULT_PYTHON_COMMAND;
    const commands = {
        sessionCommand: deepStackCursorSessionCommand(pluginDirectory, formatPathArgument, options.platform ?? process.platform),
        firstTaskCommand: `${pythonCommand} ${formatPathArgument(options.firstTaskHookPath)}`,
    };
    updateCursorHooksFile(
        options.cursorDirectory,
        configuration => mergeDeepStackCursorHooks(configuration, commands),
        { createWhenMissing: true },
    );
    return { status: 'installed', pluginDirectory, hooksPath: join(options.cursorDirectory, 'hooks.json'), warning: null };
}

/**
 * Write the Codex model sheet when this run installed the Codex plugin.
 *
 * @param {string} codexHome The Codex home.
 * @returns {string|null} The sheet path when this run created it.
 */
export function seedCodexDeepStackModels(codexHome) {
    const sheetPath = join(codexHome, DEEPSTACK_CODEX_MODEL_SHEET_NAME);
    if (existsSync(sheetPath)) return null;
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(sheetPath, 'session hook: on\n');
    return sheetPath;
}

/**
 * Install DeepStack for Claude, Codex, and Cursor.
 *
 * @param {object} [options] Install targets.
 * @param {string} [options.claudeRoot] The managed Claude root.
 * @param {string} [options.codexHome] The Codex home.
 * @param {string} [options.cursorDirectory] The Cursor home.
 * @param {string} [options.firstTaskHookPath] Absolute path of the hook the first-task command runs.
 * @param {string} [options.pythonCommand] The interpreter the installer detected.
 * @param {(pathValue: string) => string} [options.formatPathArgument] The platform path quoting.
 * @param {string} [options.sourceDirectory] A local plugin tree for the Cursor copy.
 * @param {string[]} [options.argumentList] Command-line arguments, for the opt-out flag.
 * @param {Record<string, string|undefined>} [options.environment] The process environment.
 * @param {boolean} [options.allowClone] False stops the clone fallback.
 * @param {string} [options.cloneParentDirectory] Where the temporary clone goes. Defaults to the system temp folder.
 * @param {object} [dependencies] Seams for the marketplace command runner and the clone.
 * @returns {{status: string, hosts: object[], cursor: object, warning: string|null}} The outcome.
 */
export function installDeepStackForHosts(options = {}, dependencies = {}) {
    const environment = options.environment ?? process.env;
    if (!shouldInstallMarketplacePlugin(DEEPSTACK_PLUGIN_SPEC, options.argumentList, environment)) {
        return {
            status: 'skipped',
            hosts: [],
            cursor: { status: 'skipped', pluginDirectory: null, hooksPath: null, warning: null },
            warning: null,
        };
    }
    const marketplace = installMarketplacePlugins([DEEPSTACK_PLUGIN_SPEC], {
        claudeRoot: options.claudeRoot,
        codexHome: options.codexHome,
        environment,
    }, dependencies);
    let sourceDirectory = resolveDeepStackPluginSource({
        claudeRoot: options.claudeRoot,
        codexHome: options.codexHome,
        environment,
        sourceDirectory: options.sourceDirectory,
    });
    const cloneDirectory = !sourceDirectory && options.allowClone !== false
        ? mkdtempSync(join(options.cloneParentDirectory ?? tmpdir(), DEEPSTACK_CLONE_PREFIX))
        : null;
    let cursor;
    try {
        if (cloneDirectory) {
            const cloneRepository = dependencies.cloneRepository ?? cloneDeepStackRepository;
            sourceDirectory = cloneRepository(cloneDirectory);
        }
        cursor = installDeepStackCursor({
            cursorDirectory: options.cursorDirectory,
            pluginSourceDirectory: sourceDirectory,
            firstTaskHookPath: options.firstTaskHookPath,
            pythonCommand: options.pythonCommand,
            formatPathArgument: options.formatPathArgument,
        });
    } finally {
        if (cloneDirectory) removeDeepStackClone(cloneDirectory);
    }
    if (marketplace.hosts.some(host => host.host === 'codex' && host.status === 'installed') && options.codexHome) {
        seedCodexDeepStackModels(options.codexHome);
    }
    const failed = marketplace.status === 'failed' || cursor.status === 'failed';
    const installed = marketplace.hosts.some(host => host.status === 'installed') || cursor.status === 'installed';
    return {
        status: failed ? 'failed' : (installed ? 'installed' : marketplace.status),
        hosts: marketplace.hosts,
        cursor,
        warning: [marketplace.warning, cursor.warning].filter(Boolean).join(' ') || null,
    };
}

/**
 * Clone jl-cmd-projects/DeepStack when no local tree is available.
 *
 * The installer calls this only from a full install that has no source
 * directory and no marketplace cache. Tests pass a source directory instead.
 *
 * @param {string} destination An empty directory for the clone.
 * @returns {string|null} The plugin directory inside the clone.
 */
/**
 * Remove the temporary DeepStack clone once the Cursor copy is written.
 *
 * Nothing reads the clone after the install: the Cursor hooks point at the
 * copy under the Cursor home, and Claude and Codex read their own marketplace
 * caches. Git writes its pack files read-only, which the forced removal
 * handles on Windows too.
 *
 * @param {string} cloneDirectory The directory the clone was made in.
 * @returns {void}
 */
export function removeDeepStackClone(cloneDirectory) {
    rmSync(cloneDirectory, { recursive: true, force: true, maxRetries: CLONE_REMOVAL_RETRIES });
}

/**
 * Return the git clone URL for the DeepStack marketplace repository.
 *
 * @returns {string} The clone URL.
 */
export function deepStackCloneUrl() {
    return ['https:', '', 'github.com', `${DEEPSTACK_MARKETPLACE_REPOSITORY}.git`].join('/');
}

export function cloneDeepStackRepository(destination) {
    const outcome = spawnSync('git', [
        'clone',
        '--depth',
        '1',
        deepStackCloneUrl(),
        destination,
    ], { encoding: 'utf8' });
    if (outcome.status !== 0) return null;
    const pluginDirectory = join(destination, 'plugins', DEEPSTACK_PLUGIN_NAME);
    return existsSync(join(pluginDirectory, DEEPSTACK_SKILL_RELATIVE_PATH)) ? pluginDirectory : null;
}
