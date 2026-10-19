import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import {
    ALL_CURSOR_LIFECYCLE_EVENT_NAMES,
    CURSOR_HOOKS_FILE_NAME,
    CURSOR_HOOKS_SCHEMA_VERSION,
    CURSOR_NATIVE_EVENT_NAME_BY_LEGACY_NAME,
} from './install-constants.mjs';

/**
 * Cursor reads ~/.cursor/hooks.json only in its own format: `version: 1` and a
 * `hooks` map from a camelCase event (`sessionStart`, `beforeSubmitPrompt`,
 * `stop`) to flat `{command, timeout}` entries. A Claude-style group entry
 * (`{"matcher": ..., "hooks": [...]}`) never runs, and while one is in the
 * file Cursor runs none of the file's hooks. This module turns such groups
 * into native entries and lets each package module replace only the entries
 * it owns.
 */

function isLegacyGroupEntry(entry) {
    return Boolean(entry) && typeof entry === 'object' && Array.isArray(entry.hooks) && typeof entry.command !== 'string';
}

function nativeEntriesFromLegacyGroup(group, nativeEventName) {
    const keepsMatcher = typeof group.matcher === 'string'
        && group.matcher !== ''
        && group.matcher !== '*'
        && !ALL_CURSOR_LIFECYCLE_EVENT_NAMES.has(nativeEventName);
    return group.hooks
        .filter(eachHook => eachHook && typeof eachHook.command === 'string')
        .map(eachHook => ({
            command: eachHook.command,
            ...(typeof eachHook.timeout === 'number' ? { timeout: eachHook.timeout } : {}),
            ...(keepsMatcher ? { matcher: group.matcher } : {}),
        }));
}

/**
 * Return the configuration in Cursor's native format.
 *
 * Every Claude-style group becomes one flat entry per inner command, under the
 * native event name (`SessionStart` -> `sessionStart`, `UserPromptSubmit` ->
 * `beforeSubmitPrompt`, `Stop` -> `stop`). Native entries are kept as they are.
 *
 * @param {object} configuration A parsed Cursor hooks file.
 * @returns {object} The configuration with `version` set and only native entries.
 */
export function nativeCursorHooksConfiguration(configuration) {
    const { version, hooks, ...otherFields } = configuration && typeof configuration === 'object' ? configuration : {};
    const allHooksByEvent = hooks && typeof hooks === 'object' ? hooks : {};
    const nativeHooks = {};
    for (const [eventName, allEntries] of Object.entries(allHooksByEvent)) {
        const nativeEventName = CURSOR_NATIVE_EVENT_NAME_BY_LEGACY_NAME[eventName] ?? eventName;
        if (!Array.isArray(allEntries)) {
            nativeHooks[nativeEventName] = allEntries;
            continue;
        }
        const nativeEntries = allEntries.flatMap(eachEntry => (
            isLegacyGroupEntry(eachEntry) ? nativeEntriesFromLegacyGroup(eachEntry, nativeEventName) : [eachEntry]
        ));
        nativeHooks[nativeEventName] = [...(nativeHooks[nativeEventName] ?? []), ...nativeEntries];
    }
    return { version: version ?? CURSOR_HOOKS_SCHEMA_VERSION, ...otherFields, hooks: nativeHooks };
}

function commandOf(entry) {
    return entry && typeof entry.command === 'string' ? entry.command.replace(/\\/g, '/') : '';
}

/**
 * Return the native configuration without the entries one package module owns.
 *
 * @param {object} configuration A parsed Cursor hooks file.
 * @param {(forwardSlashedCommand: string) => boolean} isOwnedCommand True for a command the caller owns.
 * @returns {object} The native configuration; an event left empty by the removal is dropped.
 */
export function withoutOwnedCursorHooks(configuration, isOwnedCommand) {
    const nativeConfiguration = nativeCursorHooksConfiguration(configuration);
    const keptHooks = {};
    for (const [eventName, allEntries] of Object.entries(nativeConfiguration.hooks)) {
        if (!Array.isArray(allEntries)) {
            keptHooks[eventName] = allEntries;
            continue;
        }
        const keptEntries = allEntries.filter(eachEntry => !isOwnedCommand(commandOf(eachEntry)));
        if (keptEntries.length > 0 || allEntries.length === 0) keptHooks[eventName] = keptEntries;
    }
    return { ...nativeConfiguration, hooks: keptHooks };
}

/**
 * Return the native configuration with exactly one copy of the caller's entries.
 *
 * @param {object} configuration A parsed Cursor hooks file.
 * @param {(forwardSlashedCommand: string) => boolean} isOwnedCommand True for a command the caller owns.
 * @param {Record<string, object[]>} allEntriesByEvent The caller's entries per native event.
 * @returns {object} The merged native configuration.
 */
export function withOwnedCursorHooks(configuration, isOwnedCommand, allEntriesByEvent) {
    const cleaned = withoutOwnedCursorHooks(configuration, isOwnedCommand);
    const mergedHooks = { ...cleaned.hooks };
    for (const [eventName, allEntries] of Object.entries(allEntriesByEvent)) {
        mergedHooks[eventName] = [...(Array.isArray(mergedHooks[eventName]) ? mergedHooks[eventName] : []), ...allEntries];
    }
    return { ...cleaned, hooks: mergedHooks };
}

/**
 * Apply one transform to `<cursorDirectory>/hooks.json` and write it when the text changes.
 *
 * @param {string} cursorDirectory The Cursor home.
 * @param {(configuration: object) => object} transform Maps the parsed file to the new one.
 * @param {{createWhenMissing?: boolean}} [options] Whether a missing file is created.
 * @returns {string|null} The hooks.json path when this call changed it.
 */
export function updateCursorHooksFile(cursorDirectory, transform, options = {}) {
    const hooksPath = join(cursorDirectory, CURSOR_HOOKS_FILE_NAME);
    const fileExists = existsSync(hooksPath);
    if (!fileExists && !options.createWhenMissing) return null;
    const currentText = fileExists ? readFileSync(hooksPath, 'utf8') : null;
    const current = currentText === null ? {} : JSON.parse(currentText.replace(/^\uFEFF/, ''));
    const updatedText = `${JSON.stringify(transform(current), null, 2)}\n`;
    if (updatedText === currentText) return null;
    mkdirSync(cursorDirectory, { recursive: true });
    writeFileSync(hooksPath, updatedText);
    return hooksPath;
}
