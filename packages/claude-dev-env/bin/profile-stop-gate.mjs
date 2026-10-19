import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH } from './install-constants.mjs';
import {
    discoverProfileSettingsPaths,
    hostConfigurationIndent,
    mergeProfileSettingsFile,
} from './merge_profile_settings.mjs';
import { normalizePathForComparison } from './resolve-install-root.mjs';

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
 * Return the gate script's path under a Claude home, in the spelling hook commands compare by.
 *
 * @param {string} claudeHome
 * @returns {string}
 */
export function gateScriptCommandFragment(claudeHome) {
    return comparableCommand(join(claudeHome, MANAGED_HOOKS_DIRECTORY_NAME, ...CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH));
}

function isGateHook(eachHook, claudeHome) {
    return typeof eachHook?.command === 'string'
        && comparableCommand(eachHook.command).includes(gateScriptCommandFragment(claudeHome));
}

/**
 * Find the open-tasks Stop gate hook the install wrote into the main settings.
 *
 * @param {string} mainSettingsPath
 * @param {string} claudeHome
 * @returns {Record<string, unknown>|null} A copy of the hook entry, or null when the main settings hold none.
 */
export function mainOpenTasksGateHook(mainSettingsPath, claudeHome) {
    if (!existsSync(mainSettingsPath)) return null;
    const settings = JSON.parse(readFileSync(mainSettingsPath, 'utf8'));
    for (const eachGroup of settings?.hooks?.[STOP_EVENT_NAME] ?? []) {
        for (const eachHook of eachGroup?.hooks ?? []) {
            if (isGateHook(eachHook, claudeHome)) return structuredClone(eachHook);
        }
    }
    return null;
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

function stopHooks(settingsPath) {
    const settingsText = readFileSync(settingsPath, 'utf8');
    if (!settingsText.trim()) return [];
    const settings = JSON.parse(settingsText);
    const stopGroups = settings?.hooks?.[STOP_EVENT_NAME];
    if (!Array.isArray(stopGroups)) return [];
    return stopGroups.flatMap((eachGroup) => (Array.isArray(eachGroup?.hooks) ? eachGroup.hooks : []));
}

function profileGateCommands(settingsPath, claudeHome) {
    return stopHooks(settingsPath)
        .filter((eachHook) => isGateHook(eachHook, claudeHome))
        .map((eachHook) => eachHook.command);
}

/**
 * True when a profile's settings.json already runs a gate script from another Claude home.
 *
 * An install with CLAUDE_CONFIG_DIR set to the profile writes a gate entry
 * for the profile's own copy of the script, and a second entry for the main
 * home's copy would run the gate twice on every stop.
 *
 * @param {string} settingsPath
 * @param {string} claudeHome
 * @returns {boolean}
 */
export function profileRunsItsOwnGate(settingsPath, claudeHome) {
    const scriptPathSuffix = `/${comparableCommand(join(MANAGED_HOOKS_DIRECTORY_NAME, ...CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH))}`;
    return stopHooks(settingsPath).some((eachHook) => typeof eachHook?.command === 'string'
        && comparableCommand(eachHook.command).includes(scriptPathSuffix)
        && !isGateHook(eachHook, claudeHome));
}

/**
 * Add the main settings' open-tasks Stop gate to every other profile's settings.json.
 *
 * A profile keeps its own settings and hooks. The merge adds the one gate
 * entry, in the spelling the main settings use, only where it is missing;
 * an entry left with an older interpreter spelling is replaced. The file as
 * it was before either change is copied to a timestamped `.bak`. A profile
 * that already runs its own copy of the gate script is left as it is.
 *
 * @param {{ mainSettingsPath: string, claudeHome: string, allProfileSettingsPaths: string[],
 *   homeDirectory: string, now?: Date }} options
 * @returns {{ settingsPath: string, additions: string[], backupPath: string|null }[]}
 */
export function addOpenTasksGateToProfiles(options) {
    const gateHook = mainOpenTasksGateHook(options.mainSettingsPath, options.claudeHome);
    if (!gateHook) return [];
    const timestamp = (options.now ?? new Date()).toISOString().replace(/[:.]/g, '-');
    const declaredSettings = [{ keyPath: ['hooks', STOP_EVENT_NAME], items: [{ hooks: [gateHook] }] }];
    const allTargetPaths = options.allProfileSettingsPaths.filter(
        (eachPath) => !profileRunsItsOwnGate(eachPath, options.claudeHome),
    );
    const allStalePaths = allTargetPaths.filter(
        (eachPath) => profileGateCommands(eachPath, options.claudeHome)
            .some((eachCommand) => eachCommand !== gateHook.command),
    );
    const originalTextByStalePath = new Map(allStalePaths.map((eachPath) => [eachPath, readFileSync(eachPath, 'utf8')]));
    removeOpenTasksGateFromProfiles({ claudeHome: options.claudeHome, allProfileSettingsPaths: allStalePaths });
    return allTargetPaths.map((eachPath) => {
        const outcome = mergeProfileSettingsFile(eachPath, {
            dryRun: false,
            homeDirectory: options.homeDirectory,
            timestamp,
            declaredSettings,
        });
        if (outcome.backupPath && originalTextByStalePath.has(eachPath)) {
            writeFileSync(outcome.backupPath, originalTextByStalePath.get(eachPath));
        }
        return outcome;
    });
}

/**
 * Remove the gate entry that points at the main Claude home from each listed profile settings path.
 *
 * Only a hook whose command runs the main home's gate script goes. A Stop
 * group left empty goes too, and so does an emptied Stop list or hooks object.
 *
 * @param {{ claudeHome: string, allProfileSettingsPaths: string[] }} options
 * @returns {string[]} The settings paths that changed.
 */
export function removeOpenTasksGateFromProfiles(options) {
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
            const keptHooks = eachGroup.hooks.filter((eachHook) => !isGateHook(eachHook, options.claudeHome));
            removedCount += eachGroup.hooks.length - keptHooks.length;
            eachGroup.hooks = keptHooks;
        }
        if (removedCount === 0) continue;
        settings.hooks[STOP_EVENT_NAME] = stopGroups.filter(
            (eachGroup) => !Array.isArray(eachGroup?.hooks) || eachGroup.hooks.length > 0,
        );
        if (settings.hooks[STOP_EVENT_NAME].length === 0) delete settings.hooks[STOP_EVENT_NAME];
        if (Object.keys(settings.hooks).length === 0) delete settings.hooks;
        writeFileSync(eachPath, JSON.stringify(settings, null, hostConfigurationIndent(settingsText, SETTINGS_INDENT)) + '\n');
        allChangedPaths.push(eachPath);
    }
    return allChangedPaths;
}
