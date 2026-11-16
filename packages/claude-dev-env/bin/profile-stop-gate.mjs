import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS } from './install-constants.mjs';
import {
    discoverProfileSettingsPaths,
    hostConfigurationIndent,
    mergeProfileSettingsFile,
} from './merge_profile_settings.mjs';
import { normalizePathForComparison } from './resolve-install-root.mjs';
import { writeFileAtomically } from './write-file-atomically.mjs';

const STOP_EVENT_NAME = 'Stop';
const MANAGED_HOOKS_DIRECTORY_NAME = 'hooks';
const SETTINGS_INDENT = '    ';

function comparablePath(filesystemPath) {
    try {
        return normalizePathForComparison(realpathSync(filesystemPath));
    } catch {
        return normalizePathForComparison(filesystemPath);
    }
}

function comparableCommand(command) {
    const forwardSlashed = command.replace(/\\/g, '/');
    return process.platform === 'win32' ? forwardSlashed.toLowerCase() : forwardSlashed;
}

/**
 * Return one gate script's path under a Claude home, in the spelling hook commands compare by.
 *
 * @param {string} claudeHome
 * @param {readonly string[]} hookRelativePath The script's path segments under the hooks directory.
 * @returns {string}
 */
export function gateScriptCommandFragment(claudeHome, hookRelativePath) {
    return comparableCommand(join(claudeHome, MANAGED_HOOKS_DIRECTORY_NAME, ...hookRelativePath));
}

function isGateHook(eachHook, claudeHome, allHookRelativePaths = ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS) {
    if (typeof eachHook?.command !== 'string') return false;
    const command = comparableCommand(eachHook.command);
    return allHookRelativePaths.some(
        (eachRelativePath) => command.includes(gateScriptCommandFragment(claudeHome, eachRelativePath)),
    );
}

function stopHooks(settingsPath) {
    const settingsText = readFileSync(settingsPath, 'utf8');
    if (!settingsText.trim()) return [];
    const settings = JSON.parse(settingsText);
    const stopGroups = settings?.hooks?.[STOP_EVENT_NAME];
    if (!Array.isArray(stopGroups)) return [];
    return stopGroups.flatMap((eachGroup) => (Array.isArray(eachGroup?.hooks) ? eachGroup.hooks : []));
}

/**
 * Find each profile Stop gate hook the install wrote into the main settings.
 *
 * The gates come back in the order of ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS.
 * A gate the main settings do not hold is left out.
 *
 * @param {string} mainSettingsPath
 * @param {string} claudeHome
 * @returns {{ hookRelativePath: readonly string[], gateHook: Record<string, unknown> }[]} A copy of each hook entry.
 */
export function mainStopGateHooks(mainSettingsPath, claudeHome) {
    if (!existsSync(mainSettingsPath)) return [];
    const allMainStopHooks = stopHooks(mainSettingsPath);
    const allMainGates = [];
    for (const eachRelativePath of ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS) {
        const gateHook = allMainStopHooks.find((eachHook) => isGateHook(eachHook, claudeHome, [eachRelativePath]));
        if (gateHook) allMainGates.push({ hookRelativePath: eachRelativePath, gateHook: structuredClone(gateHook) });
    }
    return allMainGates;
}

/**
 * List the settings.json of every other Claude profile on this machine.
 *
 * A profile whose settings.json links to the main settings already reads the
 * main hooks, so it is left out, and so is the main file itself.
 *
 * @param {{ homeDirectory: string, environment?: Record<string, string|undefined>, mainSettingsPath: string }} options
 * @returns {string[]}
 */
export function otherProfileSettingsPaths(options) {
    const mainKey = comparablePath(options.mainSettingsPath);
    const seenKeys = new Set([mainKey]);
    const allOtherPaths = [];
    for (const eachPath of discoverProfileSettingsPaths(options)) {
        if (!existsSync(eachPath)) continue;
        const pathKey = comparablePath(eachPath);
        if (seenKeys.has(pathKey)) continue;
        seenKeys.add(pathKey);
        allOtherPaths.push(eachPath);
    }
    return allOtherPaths;
}

/**
 * Split profile settings paths into the ones whose settings.json parses and the ones that do not.
 *
 * A profile file that is not valid JSON is left as it is. The caller names
 * each one, with its parse error, so the user can fix it and run the install
 * again. An empty file counts as readable.
 *
 * @param {string[]} allProfileSettingsPaths
 * @returns {{ allReadablePaths: string[], allUnreadable: { settingsPath: string, reason: string }[] }}
 */
export function splitUnreadableProfileSettings(allProfileSettingsPaths) {
    const allReadablePaths = [];
    const allUnreadable = [];
    for (const eachPath of allProfileSettingsPaths) {
        try {
            const settingsText = readFileSync(eachPath, 'utf8');
            if (settingsText.trim()) JSON.parse(settingsText);
            allReadablePaths.push(eachPath);
        } catch (readError) {
            allUnreadable.push({
                settingsPath: eachPath,
                reason: readError instanceof Error ? readError.message : String(readError),
            });
        }
    }
    return { allReadablePaths, allUnreadable };
}

/**
 * True when a settings.json that does not parse may still hold one of this Claude home's profile Stop gates.
 *
 * The raw text is searched for each gate script path, with JSON-escaped
 * backslashes read as path separators. A file that cannot be read counts as
 * one that may hold a gate.
 *
 * @param {string} settingsPath
 * @param {string} claudeHome
 * @returns {boolean}
 */
export function unparsedSettingsMayHoldGate(settingsPath, claudeHome) {
    let settingsText;
    try {
        settingsText = readFileSync(settingsPath, 'utf8');
    } catch {
        return true;
    }
    const comparableText = comparableCommand(settingsText.replace(/\\\\/g, '/'));
    return ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS.some(
        (eachRelativePath) => comparableText.includes(gateScriptCommandFragment(claudeHome, eachRelativePath)),
    );
}

function profileGateHooks(settingsPath, claudeHome, hookRelativePath) {
    return stopHooks(settingsPath).filter((eachHook) => isGateHook(eachHook, claudeHome, [hookRelativePath]));
}

/**
 * True when a profile's settings.json already runs one gate script from another Claude home.
 *
 * An install with CLAUDE_CONFIG_DIR set to the profile writes a gate entry
 * for the profile's own copy of the script, and a second entry for the main
 * home's copy would run that gate twice on every stop.
 *
 * @param {string} settingsPath
 * @param {string} claudeHome
 * @param {readonly string[]} hookRelativePath The gate script's path segments under the hooks directory.
 * @returns {boolean}
 */
export function profileRunsItsOwnGate(settingsPath, claudeHome, hookRelativePath) {
    const scriptPathSuffix = `/${comparableCommand(join(MANAGED_HOOKS_DIRECTORY_NAME, ...hookRelativePath))}`;
    return stopHooks(settingsPath).some((eachHook) => typeof eachHook?.command === 'string'
        && comparableCommand(eachHook.command).includes(scriptPathSuffix)
        && !isGateHook(eachHook, claudeHome, [hookRelativePath]));
}

function staleGateRelativePaths(settingsPath, claudeHome, allWantedGates) {
    return allWantedGates
        .filter(({ hookRelativePath, gateHook }) => profileGateHooks(settingsPath, claudeHome, hookRelativePath)
            .some((eachHook) => eachHook.command !== gateHook.command || eachHook.timeout !== gateHook.timeout))
        .map(({ hookRelativePath }) => hookRelativePath);
}

/**
 * Add each of the main settings' profile Stop gates to every other profile's settings.json.
 *
 * A profile keeps its own settings and hooks. Each gate is handled on its
 * own. The merge adds a gate entry, in the spelling the main settings use,
 * only where that gate is missing, so a profile that holds one gate gets the
 * other. An entry left with an older interpreter spelling or timeout is replaced. The
 * file as it was before either change is copied to a timestamped `.bak`. A
 * gate the profile already runs from its own copy of the script is left as
 * it is, and so is a gate the main settings do not hold.
 *
 * @param {{ mainSettingsPath: string, claudeHome: string, allProfileSettingsPaths: string[],
 *   homeDirectory: string, now?: Date }} options
 * @returns {{ settingsPath: string, additions: string[], backupPath: string|null }[]}
 */
export function addStopGatesToProfiles(options) {
    const allMainGates = mainStopGateHooks(options.mainSettingsPath, options.claudeHome);
    const timestamp = (options.now ?? new Date()).toISOString().replace(/[:.]/g, '-');
    const allOutcomes = [];
    for (const eachPath of options.allProfileSettingsPaths) {
        const allWantedGates = allMainGates.filter(
            ({ hookRelativePath }) => !profileRunsItsOwnGate(eachPath, options.claudeHome, hookRelativePath),
        );
        if (allWantedGates.length === 0) continue;
        const allStaleRelativePaths = staleGateRelativePaths(eachPath, options.claudeHome, allWantedGates);
        const originalText = readFileSync(eachPath, 'utf8');
        removeStopGatesFromProfiles({
            claudeHome: options.claudeHome,
            allProfileSettingsPaths: [eachPath],
            allHookRelativePaths: allStaleRelativePaths,
        });
        const outcome = mergeProfileSettingsFile(eachPath, {
            dryRun: false,
            homeDirectory: options.homeDirectory,
            timestamp,
            declaredSettings: [{
                keyPath: ['hooks', STOP_EVENT_NAME],
                items: allWantedGates.map(({ gateHook }) => ({ hooks: [gateHook] })),
            }],
        });
        if (outcome.backupPath && allStaleRelativePaths.length > 0) {
            writeFileSync(outcome.backupPath, originalText);
        }
        allOutcomes.push(outcome);
    }
    return allOutcomes;
}

/**
 * Remove the gate entries that point at the main Claude home from each listed profile settings path.
 *
 * Only a hook whose command runs one of the main home's gate scripts goes. A
 * Stop group left empty goes too, and so does an emptied Stop list or hooks
 * object.
 *
 * @param {{ claudeHome: string, allProfileSettingsPaths: string[],
 *   allHookRelativePaths?: readonly (readonly string[])[] }} options
 *   allHookRelativePaths limits the removal to those gates. Every profile Stop gate goes without it.
 * @returns {string[]} The settings paths that changed.
 */
export function removeStopGatesFromProfiles(options) {
    const allHookRelativePaths = options.allHookRelativePaths ?? ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS;
    const allChangedPaths = [];
    for (const eachPath of options.allProfileSettingsPaths) {
        const settingsText = readFileSync(eachPath, 'utf8');
        if (!settingsText.trim()) continue;
        const settings = JSON.parse(settingsText);
        const stopGroups = settings?.hooks?.[STOP_EVENT_NAME];
        if (!Array.isArray(stopGroups)) continue;
        let removedCount = 0;
        for (const eachGroup of stopGroups) {
            if (!Array.isArray(eachGroup?.hooks)) continue;
            const keptHooks = eachGroup.hooks.filter(
                (eachHook) => !isGateHook(eachHook, options.claudeHome, allHookRelativePaths),
            );
            removedCount += eachGroup.hooks.length - keptHooks.length;
            eachGroup.hooks = keptHooks;
        }
        if (removedCount === 0) continue;
        settings.hooks[STOP_EVENT_NAME] = stopGroups.filter(
            (eachGroup) => !Array.isArray(eachGroup?.hooks) || eachGroup.hooks.length > 0,
        );
        if (settings.hooks[STOP_EVENT_NAME].length === 0) delete settings.hooks[STOP_EVENT_NAME];
        if (Object.keys(settings.hooks).length === 0) delete settings.hooks;
        writeFileAtomically(eachPath, JSON.stringify(settings, null, hostConfigurationIndent(settingsText, SETTINGS_INDENT)) + '\n');
        allChangedPaths.push(eachPath);
    }
    return allChangedPaths;
}
