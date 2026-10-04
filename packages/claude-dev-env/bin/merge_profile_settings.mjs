/**
 * Add the declared profile settings entries to every Claude profile settings.json.
 *
 * Each declared entry is one item in a list at a key path, such as one rule in
 * `permissions.allow`. The merge adds an item only when the list lacks it, so a
 * second run changes nothing and every other key stays as the file holds it.
 * Before the first change to a file, the merge copies that file to a
 * timestamped `.bak` beside it.
 *
 * Run `node merge_profile_settings.mjs --dry-run` to list the additions for
 * every profile on this machine without writing anything.
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
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
export const SESSION_TITLE_GATE_FILE_NAME = 'session_title_status_gate.py';
export const SESSION_TITLE_GATE_SOURCE_DIRECTORY = fileURLToPath(new URL('../profile-settings/', import.meta.url));
export const ALL_SESSION_TITLE_GATE_RELATIVE_PATHS = Object.freeze([
    SESSION_TITLE_GATE_FILE_NAME,
    join('config', '__init__.py'),
    join('config', 'session_title_gate_constants.py'),
]);
export const SESSION_TITLE_GATE_COMMAND = `python3 ~/.claude/${SESSION_TITLE_GATE_FILE_NAME}`;
export const AUTO_MODE_DEFAULTS_ENTRY = '$defaults';

const DEFAULT_SETTINGS_INDENT = '    ';
const DEFAULT_HOST_CONFIGURATION_INDENT = '  ';

/**
 * @typedef {{ keyPath: string[], items: unknown[] }} DeclaredListEntries
 */

/** @type {readonly DeclaredListEntries[]} */
export const DECLARED_PROFILE_SETTINGS = Object.freeze([
    {
        keyPath: ['hooks', 'Stop'],
        items: [
            {
                hooks: [
                    { type: 'command', command: SESSION_TITLE_GATE_COMMAND, timeout: 10 },
                ],
            },
        ],
    },
    {
        keyPath: ['permissions', 'allow'],
        items: [
            'mcp__claude-code-remote__set_session_title',
            'mcp__ccd_session_mgmt__set_session_title',
            `Bash(${SESSION_TITLE_GATE_COMMAND}:*)`,
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

/**
 * Add each declared item its list lacks, in place.
 *
 * A hook group counts as present when every command it declares already runs
 * somewhere in that event, compared through hookCommandComparisonKey, because
 * the installer rewrites `~/` to an absolute home path. Every other item counts as
 * present when the list holds an equal string.
 *
 * @param {Record<string, unknown>} settings Mutated in place.
 * @param {readonly DeclaredListEntries[]} declaredSettings
 * @param {string} homeDirectory
 * @returns {string[]} One `<key path>: <item>` line per added item.
 */
export function mergeDeclaredProfileSettings(settings, declaredSettings, homeDirectory) {
    const allAdditions = [];
    for (const { keyPath, items } of declaredSettings) {
        const targetList = listAtKeyPath(settings, keyPath);
        for (const eachItem of items) {
            if (listHoldsItem(targetList, eachItem, homeDirectory)) continue;
            targetList.push(structuredClone(eachItem));
            allAdditions.push(`${keyPath.join('.')}: ${JSON.stringify(eachItem)}`);
        }
    }
    return allAdditions;
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
    const additions = mergeDeclaredProfileSettings(
        settings,
        options.declaredSettings ?? DECLARED_PROFILE_SETTINGS,
        options.homeDirectory,
    );
    if (additions.length === 0 || options.dryRun) {
        return { settingsPath, additions, backupPath: null };
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
    return { settingsPath, additions, backupPath };
}

/**
 * Copy the session-title gate and its constants module to `~/.claude` when a copy is absent or differs.
 *
 * The Stop hook entry runs the gate, so both files have to land before the entry does.
 *
 * @param {{ homeDirectory: string, dryRun: boolean }} options
 * @returns {{ gatePath: string, changed: boolean }}
 */
export function installSessionTitleGate(options) {
    const claudeDirectory = join(options.homeDirectory, DEFAULT_CLAUDE_DIRECTORY_NAME);
    const allStaleRelativePaths = ALL_SESSION_TITLE_GATE_RELATIVE_PATHS.filter((eachRelativePath) => {
        const targetPath = join(claudeDirectory, eachRelativePath);
        const sourceText = readFileSync(join(SESSION_TITLE_GATE_SOURCE_DIRECTORY, eachRelativePath), 'utf8');
        return !existsSync(targetPath) || readFileSync(targetPath, 'utf8') !== sourceText;
    });
    if (!options.dryRun) {
        for (const eachRelativePath of allStaleRelativePaths) {
            const targetPath = join(claudeDirectory, eachRelativePath);
            mkdirSync(dirname(targetPath), { recursive: true });
            copyFileSync(join(SESSION_TITLE_GATE_SOURCE_DIRECTORY, eachRelativePath), targetPath);
        }
    }
    return {
        gatePath: join(claudeDirectory, SESSION_TITLE_GATE_FILE_NAME),
        changed: allStaleRelativePaths.length > 0,
    };
}

/**
 * Install the gate, then merge the declared entries into each settings.json.
 *
 * @param {string[]} allSettingsPaths
 * @param {{ dryRun: boolean, homeDirectory: string, now?: Date }} options
 * @returns {{ gate: { gatePath: string, changed: boolean },
 *   files: { settingsPath: string, additions: string[], backupPath: string | null }[] }}
 */
export function mergeProfileSettings(allSettingsPaths, options) {
    const timestamp = (options.now ?? new Date()).toISOString().replace(/[:.]/g, '-');
    const gate = installSessionTitleGate(options);
    const files = allSettingsPaths.map((eachPath) => mergeProfileSettingsFile(eachPath, {
        dryRun: options.dryRun,
        homeDirectory: options.homeDirectory,
        timestamp,
    }));
    return { gate, files };
}

/**
 * @param {{ gate: { gatePath: string, changed: boolean },
 *   files: { settingsPath: string, additions: string[], backupPath: string | null }[] }} outcome
 * @param {boolean} isDryRun
 * @returns {string[]}
 */
export function describeProfileSettingsOutcome(outcome, isDryRun) {
    const verb = isDryRun ? 'would add' : 'added';
    const allLines = [
        outcome.gate.changed
            ? `${outcome.gate.gatePath}: ${isDryRun ? 'would copy' : 'copied'} session-title gate`
            : `${outcome.gate.gatePath}: gate current`,
    ];
    for (const { settingsPath, additions, backupPath } of outcome.files) {
        if (additions.length === 0) {
            allLines.push(`${settingsPath}: no change`);
            continue;
        }
        allLines.push(`${settingsPath}: ${verb} ${additions.length}${backupPath ? ` (backup ${backupPath})` : ''}`);
        allLines.push(...additions.map((eachAddition) => `  ${eachAddition}`));
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
