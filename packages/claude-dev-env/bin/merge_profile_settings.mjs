/**
 * Add the declared profile settings entries to every Claude profile settings.json.
 *
 * Each declared entry is one item in a list at a key path, such as one rule in
 * `permissions.allow`. The merge adds an item only when the list lacks it, so a
 * second run changes nothing and every other key stays as the file holds it.
 * Before the first change to a file, the merge copies that file to a
 * timestamped `.bak` beside it.
 *
 * Each run also retires the profile-level session-title Stop gate an earlier
 * install copied to `~/.claude`. The plugin's own session-title stop gate does
 * that job, so the merge removes the profile gate's Stop hook and allow rule
 * from each file and deletes the gate files.
 *
 * Run `node merge_profile_settings.mjs --dry-run` to list the changes for
 * every profile on this machine without writing anything.
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expandHomeDirectoryTokens } from './expand_home_directory_tokens.mjs';
import { SETTINGS_FILE_NAME } from './install-constants.mjs';
import {
    CLAUDE_CONFIG_DIR_ENVIRONMENT_VARIABLE,
    DEFAULT_CLAUDE_DIRECTORY_NAME,
    normalizePathForComparison,
} from './resolve-install-root.mjs';
import { resolveProfilesRootDirectory } from './select-install-targets.mjs';

export const DRY_RUN_FLAG = '--dry-run';
export const RETIRED_SESSION_TITLE_GATE_FILE_NAME = 'session_title_status_gate.py';
export const RETIRED_SESSION_TITLE_GATE_CONFIG_DIRECTORY_NAME = 'config';
export const RETIRED_SESSION_TITLE_GATE_CONSTANTS_FILE_NAME = 'session_title_gate_constants.py';
export const RETIRED_SESSION_TITLE_GATE_PACKAGE_INIT_TEXT =
    '"""Constants package installed beside the Stop hook gate."""\n';
export const RETIRED_SESSION_TITLE_GATE_COMMAND = `python3 ~/.claude/${RETIRED_SESSION_TITLE_GATE_FILE_NAME}`;
export const RETIRED_SESSION_TITLE_GATE_PERMISSION = `Bash(${RETIRED_SESSION_TITLE_GATE_COMMAND}:*)`;
export const AUTO_MODE_DEFAULTS_ENTRY = '$defaults';

const DEFAULT_SETTINGS_INDENT = '    ';
const DEFAULT_HOST_CONFIGURATION_INDENT = '  ';

/**
 * @typedef {{ keyPath: string[], items: unknown[] }} DeclaredListEntries
 */

/** @type {readonly DeclaredListEntries[]} */
export const DECLARED_PROFILE_SETTINGS = Object.freeze([
    {
        keyPath: ['permissions', 'allow'],
        items: [
            'mcp__claude-code-remote__set_session_title',
            'mcp__ccd_session_mgmt__set_session_title',
            'Bash(python ~/.claude/scripts/account_broker.py run:*)',
        ],
    },
    {
        keyPath: ['autoMode', 'allow'],
        items: [
            AUTO_MODE_DEFAULTS_ENTRY,
            'Setting this session\'s title with the set_session_title MCP tool '
                + '(mcp__claude-code-remote__set_session_title or mcp__ccd_session_mgmt__set_session_title) is allowed, '
                + 'and so is a live test run of the account broker with '
                + '`python ~/.claude/scripts/account_broker.py run`: the user installed both tools for these sessions',
        ],
    },
]);

/**
 * List every Claude profile settings.json on this machine.
 *
 * The main profile and the `CLAUDE_CONFIG_DIR` profile count when their
 * directory exists, so a missing settings.json there is created. A directory
 * under the profiles root counts only when it already holds a settings.json,
 * which skips agents homes and other non-profile folders kept beside them.
 *
 * @param {{ homeDirectory: string, environment?: Record<string, string | undefined> }} options
 * @returns {string[]} Absolute settings.json paths, one per profile.
 */
export function discoverProfileSettingsPaths(options) {
    const environment = options.environment ?? {};
    const allProfileDirectories = [join(options.homeDirectory, DEFAULT_CLAUDE_DIRECTORY_NAME)];
    const configDirectory = environment[CLAUDE_CONFIG_DIR_ENVIRONMENT_VARIABLE]?.trim();
    if (configDirectory) {
        allProfileDirectories.push(configDirectory);
    }
    const profilesRoot = resolveProfilesRootDirectory({
        homeDirectory: options.homeDirectory,
        environment,
    });
    const allSettingsPaths = allProfileDirectories
        .filter((eachDirectory) => existsSync(eachDirectory))
        .map((eachDirectory) => resolve(eachDirectory, SETTINGS_FILE_NAME));
    if (existsSync(profilesRoot)) {
        for (const eachEntry of readdirSync(profilesRoot, { withFileTypes: true })) {
            const settingsPath = join(profilesRoot, eachEntry.name, SETTINGS_FILE_NAME);
            if (eachEntry.isDirectory() && existsSync(settingsPath)) {
                allSettingsPaths.push(resolve(settingsPath));
            }
        }
    }
    const seenKeys = new Set();
    return allSettingsPaths.filter((eachPath) => {
        const comparisonKey = normalizePathForComparison(eachPath);
        if (seenKeys.has(comparisonKey)) return false;
        seenKeys.add(comparisonKey);
        return true;
    });
}

export function mergeDeclaredProfileSettings(settings, declaredSettings, homeDirectory) {
    const allAdditions = [];
    for (const { keyPath, items } of declaredSettings) {
        const targetList = listAtKeyPath(settings, keyPath);
        for (const eachItem of items) {
            if (listHoldsItem(targetList, eachItem, homeDirectory)) continue;
            const addedItem = itemWithExpandedHookCommands(eachItem, homeDirectory);
            targetList.push(addedItem);
            allAdditions.push(`${keyPath.join('.')}: ${JSON.stringify(addedItem)}`);
        }
    }
    return allAdditions;
}

/**
 * Remove the retired profile gate's Stop hook and allow rule from one settings object.
 *
 * A Stop group left with no hook goes too, and so does an emptied Stop list or
 * hooks object, so the file holds no husk of the retired entry.
 *
 * @param {Record<string, any>} settings
 * @param {string} homeDirectory
 * @returns {string[]} One description per removed entry.
 */
export function removeRetiredSessionTitleGate(settings, homeDirectory) {
    const allRemovals = [];
    const retiredCommandKey = hookCommandComparisonKey(RETIRED_SESSION_TITLE_GATE_COMMAND, homeDirectory);
    const hooks = settings.hooks;
    if (hooks && typeof hooks === 'object' && Array.isArray(hooks.Stop)) {
        for (const eachGroup of hooks.Stop) {
            if (!Array.isArray(eachGroup?.hooks)) continue;
            eachGroup.hooks = eachGroup.hooks.filter((eachHook) => {
                const isRetired = typeof eachHook?.command === 'string'
                    && hookCommandComparisonKey(eachHook.command, homeDirectory) === retiredCommandKey;
                if (isRetired) allRemovals.push(`hooks.Stop: ${eachHook.command}`);
                return !isRetired;
            });
        }
        hooks.Stop = hooks.Stop.filter((eachGroup) => !Array.isArray(eachGroup?.hooks) || eachGroup.hooks.length > 0);
        if (hooks.Stop.length === 0) delete hooks.Stop;
        if (Object.keys(hooks).length === 0) delete settings.hooks;
    }
    const allowList = settings.permissions?.allow;
    if (Array.isArray(allowList) && allowList.includes(RETIRED_SESSION_TITLE_GATE_PERMISSION)) {
        settings.permissions.allow = allowList.filter((eachRule) => eachRule !== RETIRED_SESSION_TITLE_GATE_PERMISSION);
        allRemovals.push(`permissions.allow: ${RETIRED_SESSION_TITLE_GATE_PERMISSION}`);
    }
    return allRemovals;
}

/**
 * Merge the declared entries into one settings.json.
 *
 * @param {string} settingsPath
 * @param {{ dryRun: boolean, homeDirectory: string, timestamp: string,
 *   declaredSettings?: readonly DeclaredListEntries[] }} options
 * @returns {{ settingsPath: string, additions: string[], backupPath: string | null }}
 */
export function mergeProfileSettingsFile(settingsPath, options) {
    const settingsText = existsSync(settingsPath) ? readFileSync(settingsPath, 'utf8') : '';
    const settings = settingsText.trim() ? JSON.parse(settingsText) : {};
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new Error(`${settingsPath} holds a value other than a JSON object`);
    }
    const removals = removeRetiredSessionTitleGate(settings, options.homeDirectory);
    const additions = mergeDeclaredProfileSettings(
        settings,
        options.declaredSettings ?? DECLARED_PROFILE_SETTINGS,
        options.homeDirectory,
    );
    if ((additions.length === 0 && removals.length === 0) || options.dryRun) {
        return { settingsPath, additions, removals, backupPath: null };
    }
    let backupPath = null;
    if (settingsText) {
        backupPath = `${settingsPath}.${options.timestamp}.bak`;
        copyFileSync(settingsPath, backupPath);
    }
    mkdirSync(dirname(settingsPath), { recursive: true });
    writeFileSync(
        settingsPath,
        JSON.stringify(settings, null, hostConfigurationIndent(settingsText, DEFAULT_SETTINGS_INDENT)) + '\n',
    );
    return { settingsPath, additions, removals, backupPath };
}

/**
 * Delete the retired profile gate and its constants package from `~/.claude`.
 *
 * The package's `__init__.py` goes only while it still holds the text the
 * installer wrote, and the config directory goes only once nothing else is
 * left in it, so a user's own files there stay.
 *
 * @param {{ homeDirectory: string, dryRun: boolean }} options
 * @returns {{ removedPaths: string[] }}
 */
export function retireSessionTitleGate(options) {
    const claudeDirectory = join(options.homeDirectory, DEFAULT_CLAUDE_DIRECTORY_NAME);
    const configDirectory = join(claudeDirectory, RETIRED_SESSION_TITLE_GATE_CONFIG_DIRECTORY_NAME);
    const packageInitPath = join(configDirectory, '__init__.py');
    const allRetiredPaths = [
        join(claudeDirectory, RETIRED_SESSION_TITLE_GATE_FILE_NAME),
        join(configDirectory, RETIRED_SESSION_TITLE_GATE_CONSTANTS_FILE_NAME),
    ];
    if (existsSync(packageInitPath) && readFileSync(packageInitPath, 'utf8') === RETIRED_SESSION_TITLE_GATE_PACKAGE_INIT_TEXT) {
        allRetiredPaths.push(packageInitPath);
    }
    const removedPaths = allRetiredPaths.filter((eachPath) => existsSync(eachPath));
    if (options.dryRun) {
        return { removedPaths };
    }
    for (const eachPath of removedPaths) {
        rmSync(eachPath);
    }
    if (existsSync(configDirectory)) {
        const allLeftEntries = readdirSync(configDirectory).filter((eachName) => eachName !== '__pycache__');
        if (allLeftEntries.length === 0) {
            rmSync(configDirectory, { recursive: true, force: true });
        }
    }
    return { removedPaths };
}

/**
 * Retire the profile gate, then merge the declared entries into each settings.json.
 *
 * @param {string[]} allSettingsPaths
 * @param {{ dryRun: boolean, homeDirectory: string, now?: Date }} options
 * @returns {{ gate: { removedPaths: string[] },
 *   files: { settingsPath: string, additions: string[], removals: string[], backupPath: string | null }[] }}
 */
export function mergeProfileSettings(allSettingsPaths, options) {
    const timestamp = (options.now ?? new Date()).toISOString().replace(/[:.]/g, '-');
    const gate = retireSessionTitleGate(options);
    const files = allSettingsPaths.map((eachPath) => mergeProfileSettingsFile(eachPath, {
        dryRun: options.dryRun,
        homeDirectory: options.homeDirectory,
        timestamp,
    }));
    return { gate, files };
}

/**
 * @param {{ gate: { removedPaths: string[] },
 *   files: { settingsPath: string, additions: string[], removals: string[], backupPath: string | null }[] }} outcome
 * @param {boolean} isDryRun
 * @returns {string[]}
 */
export function describeProfileSettingsOutcome(outcome, isDryRun) {
    const addVerb = isDryRun ? 'would add' : 'added';
    const removeVerb = isDryRun ? 'would remove' : 'removed';
    const allLines = outcome.gate.removedPaths.map(
        (eachPath) => `${eachPath}: ${removeVerb} retired session-title gate file`,
    );
    for (const { settingsPath, additions, removals, backupPath } of outcome.files) {
        if (additions.length === 0 && removals.length === 0) {
            allLines.push(`${settingsPath}: no change`);
            continue;
        }
        const backupNote = backupPath ? ` (backup ${backupPath})` : '';
        allLines.push(`${settingsPath}: ${addVerb} ${additions.length}, ${removeVerb} ${removals.length}${backupNote}`);
        allLines.push(...additions.map((eachAddition) => `  + ${eachAddition}`));
        allLines.push(...removals.map((eachRemoval) => `  - ${eachRemoval}`));
    }
    return allLines;
}

/**
 * @param {Record<string, unknown>} settings
 * @param {string[]} keyPath
 * @returns {unknown[]}
 */
function listAtKeyPath(settings, keyPath) {
    let container = settings;
    for (const eachKey of keyPath.slice(0, -1)) {
        const child = container[eachKey];
        if (!child || typeof child !== 'object' || Array.isArray(child)) {
            container[eachKey] = {};
        }
        container = /** @type {Record<string, unknown>} */ (container[eachKey]);
    }
    const listKey = keyPath[keyPath.length - 1];
    if (!Array.isArray(container[listKey])) {
        container[listKey] = [];
    }
    return /** @type {unknown[]} */ (container[listKey]);
}

/**
 * @param {unknown[]} targetList
 * @param {unknown} item
 * @param {string} homeDirectory
 * @returns {boolean}
 */
function listHoldsItem(targetList, item, homeDirectory) {
    if (typeof item === 'string') {
        return targetList.includes(item);
    }
    const presentCommands = new Set(
        targetList.flatMap((eachGroup) => groupCommands(eachGroup, homeDirectory)),
    );
    return groupCommands(item, homeDirectory).every((eachCommand) => presentCommands.has(eachCommand));
}

/**
 * Copy one declared item, spelling each hook command the way the installer writes it.
 *
 * The installer rewrites every hook command's home tokens to the absolute home
 * path on each run. Writing that same spelling here keeps a second install from
 * rewriting the entry this merge added.
 *
 * @param {unknown} item
 * @param {string} homeDirectory
 * @returns {unknown}
 */
function itemWithExpandedHookCommands(item, homeDirectory) {
    const addedItem = structuredClone(item);
    const allHooks = Array.isArray(addedItem?.hooks) ? addedItem.hooks : [];
    for (const eachHook of allHooks) {
        if (typeof eachHook?.command === 'string') {
            eachHook.command = expandHomeDirectoryTokens(eachHook.command, homeDirectory);
        }
    }
    return addedItem;
}

/**
 * @param {unknown} group
 * @param {string} homeDirectory
 * @returns {string[]}
 */
function groupCommands(group, homeDirectory) {
    const allHooks = Array.isArray(group?.hooks) ? group.hooks : [];
    return allHooks
        .map((eachHook) => eachHook?.command)
        .filter((eachCommand) => typeof eachCommand === 'string')
        .map((eachCommand) => hookCommandComparisonKey(eachCommand, homeDirectory));
}

/**
 * Spell a hook command the way both the installer and this merge can compare it.
 *
 * Home tokens expand to the one home directory, backslashes become forward
 * slashes, and on Windows case folds, the same rule normalizePathForComparison
 * applies to a path.
 *
 * @param {string} command
 * @param {string} homeDirectory
 * @returns {string}
 */
function hookCommandComparisonKey(command, homeDirectory) {
    const forwardSlashed = expandHomeDirectoryTokens(command, homeDirectory).replace(/\\/g, '/');
    return process.platform === 'win32' ? forwardSlashed.toLowerCase() : forwardSlashed;
}

/**
 * Read the indent the host configuration file already uses.
 *
 * ~/.claude/settings.json uses four spaces and ~/.codex/hooks.json uses two.
 * Forcing four spaces would rewrite every line of one of those files. The first
 * indented line supplies the indent, tabs included.
 *
 * @param {string} settingsText The host configuration file as it stands on disk.
 * @param {string} [defaultIndent] The indent for a file with no indented line.
 * @returns {string} The indent one nesting level uses.
 */
export function hostConfigurationIndent(settingsText, defaultIndent = DEFAULT_HOST_CONFIGURATION_INDENT) {
    const firstIndentedLine = /\n([ \t]+)\S/.exec(settingsText);
    return firstIndentedLine ? firstIndentedLine[1] : defaultIndent;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const isDryRun = process.argv.slice(2).includes(DRY_RUN_FLAG);
    const homeDirectory = homedir();
    const outcome = mergeProfileSettings(
        discoverProfileSettingsPaths({ homeDirectory, environment: process.env }),
        { dryRun: isDryRun, homeDirectory },
    );
    for (const eachLine of describeProfileSettingsOutcome(outcome, isDryRun)) {
        console.log(eachLine);
    }
}
