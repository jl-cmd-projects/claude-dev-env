import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import {
    CURSOR_GUIDANCE_HOOK_RELATIVE_PATH,
    CURSOR_GUIDANCE_SESSION_MATCHER,
    CURSOR_HOOK_TIMEOUT_SECONDS,
    CURSOR_HOOKS_FILE_NAME,
    CURSOR_HOOKS_SCHEMA_VERSION,
    CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH,
} from './install-constants.mjs';

const DEFAULT_PYTHON_COMMAND = 'python3';
const MANAGED_SCRIPT_NAMES = [
    CURSOR_GUIDANCE_HOOK_RELATIVE_PATH.at(-1),
    CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH.at(-1),
];

function quotedPath(pathValue) {
    return `'${pathValue.replaceAll("'", "'\\''")}'`;
}

function namesManagedScript(hookGroup) {
    const groupText = JSON.stringify(hookGroup);
    return MANAGED_SCRIPT_NAMES.some(eachName => groupText.includes(eachName));
}

function groupsWithout(allGroups) {
    return Array.isArray(allGroups) ? allGroups.filter(eachGroup => !namesManagedScript(eachGroup)) : [];
}

function commandGroup(matcher, command) {
    return { matcher, hooks: [{ type: 'command', command, timeout: CURSOR_HOOK_TIMEOUT_SECONDS }] };
}

/**
 * Return the Cursor hooks configuration without the agents guidance hooks.
 *
 * @param {object} configuration The parsed ~/.cursor/hooks.json.
 * @returns {object} The configuration with both managed groups removed.
 */
export function withoutCursorAgentsGuidanceHooks(configuration) {
    const hooks = configuration.hooks && typeof configuration.hooks === 'object' ? configuration.hooks : {};
    return {
        ...configuration,
        hooks: { ...hooks, SessionStart: groupsWithout(hooks.SessionStart), Stop: groupsWithout(hooks.Stop) },
    };
}

/**
 * Return the Cursor hooks configuration with one guidance SessionStart group and one open tasks Stop group.
 *
 * Cursor keeps user rules in app settings, so the SessionStart hook feeds the
 * installed AGENTS.md to every session. The Stop group runs the open tasks gate.
 *
 * @param {object} configuration The parsed ~/.cursor/hooks.json.
 * @param {{guidanceCommand: string, openTasksCommand: string}} commands The two hook commands.
 * @returns {object} The merged configuration.
 */
export function mergeCursorAgentsGuidanceHooks(configuration, commands) {
    const cleaned = withoutCursorAgentsGuidanceHooks(configuration);
    return {
        version: CURSOR_HOOKS_SCHEMA_VERSION,
        ...cleaned,
        hooks: {
            ...cleaned.hooks,
            SessionStart: [...cleaned.hooks.SessionStart, commandGroup(CURSOR_GUIDANCE_SESSION_MATCHER, commands.guidanceCommand)],
            Stop: [...cleaned.hooks.Stop, commandGroup('', commands.openTasksCommand)],
        },
    };
}

function readHooksConfiguration(hooksPath) {
    return existsSync(hooksPath) ? JSON.parse(readFileSync(hooksPath, 'utf8')) : { hooks: {} };
}

function writeWhenChanged(hooksPath, updatedConfiguration) {
    const updatedText = `${JSON.stringify(updatedConfiguration, null, 2)}\n`;
    if (existsSync(hooksPath) && readFileSync(hooksPath, 'utf8') === updatedText) return null;
    writeFileSync(hooksPath, updatedText);
    return hooksPath;
}

/**
 * Register the agents guidance and open tasks hooks in the Cursor home.
 *
 * The commands use the interpreter the installer detected, the same one the
 * Claude and Codex hooks use, so a Windows install runs the resolved
 * `python.exe` path and not the Microsoft Store `python3` stub.
 *
 * @param {{cursorDirectory: string, hooksDirectory: string, guidancePath: string, pythonCommand?: string, formatPathArgument?: (pathValue: string) => string}} options Install paths, the detected interpreter, and the platform path quoting.
 * @returns {string|null} The hooks.json path when this run changed it.
 */
export function writeCursorAgentsGuidanceHooks(options) {
    const hooksPath = join(options.cursorDirectory, CURSOR_HOOKS_FILE_NAME);
    const current = readHooksConfiguration(hooksPath);
    const pythonCommand = options.pythonCommand ?? DEFAULT_PYTHON_COMMAND;
    const formatPathArgument = options.formatPathArgument ?? quotedPath;
    const guidanceScript = join(options.hooksDirectory, ...CURSOR_GUIDANCE_HOOK_RELATIVE_PATH);
    const openTasksScript = join(options.hooksDirectory, ...CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH);
    const merged = mergeCursorAgentsGuidanceHooks(current, {
        guidanceCommand: `${pythonCommand} ${formatPathArgument(guidanceScript)} ${formatPathArgument(options.guidancePath)}`,
        openTasksCommand: `${pythonCommand} ${formatPathArgument(openTasksScript)}`,
    });
    mkdirSync(options.cursorDirectory, { recursive: true });
    return writeWhenChanged(hooksPath, merged);
}

/**
 * Remove the agents guidance and open tasks hooks from the Cursor home.
 *
 * @param {string} cursorDirectory The Cursor home.
 * @returns {string|null} The hooks.json path when this run changed it.
 */
export function removeCursorAgentsGuidanceHooks(cursorDirectory) {
    const hooksPath = join(cursorDirectory, CURSOR_HOOKS_FILE_NAME);
    if (!existsSync(hooksPath)) return null;
    return writeWhenChanged(hooksPath, withoutCursorAgentsGuidanceHooks(readHooksConfiguration(hooksPath)));
}
