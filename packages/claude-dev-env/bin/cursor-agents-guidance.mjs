import { join } from 'node:path';

import {
    CURSOR_GUIDANCE_HOOK_RELATIVE_PATH,
    CURSOR_HOOK_TIMEOUT_SECONDS,
    CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH,
    CURSOR_SESSION_START_EVENT,
    CURSOR_STOP_EVENT,
} from './install-constants.mjs';
import { updateCursorHooksFile, withOwnedCursorHooks, withoutOwnedCursorHooks } from './cursor-native-hooks.mjs';

const DEFAULT_PYTHON_COMMAND = 'python3';
const OWNED_SCRIPT_NAMES = [
    CURSOR_GUIDANCE_HOOK_RELATIVE_PATH.at(-1),
    CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH.at(-1),
];

function quotedPath(pathValue) {
    return `'${pathValue.replaceAll("'", "'\\''")}'`;
}

/**
 * True for a Cursor hook command this module owns.
 *
 * @param {string} forwardSlashedCommand A hook command with forward slashes.
 * @returns {boolean} True when the command runs the guidance hook or the open tasks gate.
 */
export function isAgentsGuidanceCommand(forwardSlashedCommand) {
    return OWNED_SCRIPT_NAMES.some(eachName => forwardSlashedCommand.includes(eachName));
}

/**
 * Return the Cursor hooks configuration, in native format, without the agents guidance hooks.
 *
 * @param {object} configuration The parsed ~/.cursor/hooks.json.
 * @returns {object} The configuration with both owned entries removed.
 */
export function withoutCursorAgentsGuidanceHooks(configuration) {
    return withoutOwnedCursorHooks(configuration, isAgentsGuidanceCommand);
}

/**
 * Return the Cursor hooks configuration with one guidance `sessionStart` entry and one open tasks `stop` entry.
 *
 * The `sessionStart` hook returns the installed AGENTS.md as `additional_context`,
 * which Cursor adds to the session's context. The `stop` hook runs the open
 * tasks gate, whose `followup_message` Cursor submits as the next user message.
 *
 * @param {object} configuration The parsed ~/.cursor/hooks.json.
 * @param {{guidanceCommand: string, openTasksCommand: string}} commands The two hook commands.
 * @returns {object} The merged native configuration.
 */
export function mergeCursorAgentsGuidanceHooks(configuration, commands) {
    return withOwnedCursorHooks(configuration, isAgentsGuidanceCommand, {
        [CURSOR_SESSION_START_EVENT]: [{ command: commands.guidanceCommand, timeout: CURSOR_HOOK_TIMEOUT_SECONDS }],
        [CURSOR_STOP_EVENT]: [{ command: commands.openTasksCommand, timeout: CURSOR_HOOK_TIMEOUT_SECONDS }],
    });
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
    const pythonCommand = options.pythonCommand ?? DEFAULT_PYTHON_COMMAND;
    const formatPathArgument = options.formatPathArgument ?? quotedPath;
    const guidanceScript = join(options.hooksDirectory, ...CURSOR_GUIDANCE_HOOK_RELATIVE_PATH);
    const openTasksScript = join(options.hooksDirectory, ...CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH);
    const commands = {
        guidanceCommand: `${pythonCommand} ${formatPathArgument(guidanceScript)} ${formatPathArgument(options.guidancePath)}`,
        openTasksCommand: `${pythonCommand} ${formatPathArgument(openTasksScript)}`,
    };
    return updateCursorHooksFile(
        options.cursorDirectory,
        configuration => mergeCursorAgentsGuidanceHooks(configuration, commands),
        { createWhenMissing: true },
    );
}

/**
 * Remove the agents guidance and open tasks hooks from the Cursor home.
 *
 * @param {string} cursorDirectory The Cursor home.
 * @returns {string|null} The hooks.json path when this run changed it.
 */
export function removeCursorAgentsGuidanceHooks(cursorDirectory) {
    return updateCursorHooksFile(cursorDirectory, withoutCursorAgentsGuidanceHooks);
}
