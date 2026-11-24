import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import {
    ANTIGRAVITY_HOOKS_ENTRY_NAME,
    ANTIGRAVITY_HOOKS_FILE_NAME,
    ANTIGRAVITY_HOOK_BRIDGE_SCRIPT_NAME,
    ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
} from './install-constants.mjs';

const DEFAULT_PYTHON_COMMAND = 'python3';

function defaultQuotedPath(pathValue) {
    return `'${pathValue.replaceAll("'", "'\\''")}'`;
}

/**
 * Build the Antigravity hooks.json entry that delegates lifecycle events to
 * the installed Claude/Codex hook bridge script.
 *
 * @param {{scriptsDirectory: string, claudeHomeDirectory: string, pythonCommand?: string, formatPathArgument?: (pathValue: string) => string}} options Install paths, detected Python interpreter, and platform path quoting.
 * @returns {object} One named Antigravity hook entry covering all bridged events.
 */
export function buildAntigravityHookEntry(options) {
    const pythonCommand = options.pythonCommand || DEFAULT_PYTHON_COMMAND;
    const formatPath = options.formatPathArgument ?? defaultQuotedPath;
    const bridgeScript = formatPath(join(options.scriptsDirectory, ANTIGRAVITY_HOOK_BRIDGE_SCRIPT_NAME));
    const claudeHomeArgument = formatPath(options.claudeHomeDirectory);
    const commandFor = eventName => `${pythonCommand} ${bridgeScript} --event ${eventName} --scope global --claude-home ${claudeHomeArgument}`;

    return {
        SessionStart: [
            {
                type: 'command',
                command: commandFor('SessionStart'),
                timeout: ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
            },
        ],
        PreInvocation: [
            {
                type: 'command',
                command: commandFor('PreInvocation'),
                timeout: ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
            },
        ],
        PreToolUse: [
            {
                matcher: '*',
                hooks: [
                    {
                        type: 'command',
                        command: commandFor('PreToolUse'),
                        timeout: ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
                    },
                ],
            },
        ],
        PostToolUse: [
            {
                matcher: '*',
                hooks: [
                    {
                        type: 'command',
                        command: commandFor('PostToolUse'),
                        timeout: ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
                    },
                ],
            },
        ],
        Stop: [
            {
                type: 'command',
                command: commandFor('Stop'),
                timeout: ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
            },
        ],
    };
}

/**
 * Return the Antigravity hooks configuration with the claude-dev-env entry
 * updated while leaving every other named hook entry untouched.
 *
 * @param {object} configuration Parsed ~/.gemini/config/hooks.json object.
 * @param {object} entry The claude-dev-env hook entry to store.
 * @returns {object} Updated configuration object.
 */
export function mergeAntigravityHooks(configuration, entry) {
    const base = configuration && typeof configuration === 'object' && !Array.isArray(configuration)
        ? { ...configuration }
        : {};
    base[ANTIGRAVITY_HOOKS_ENTRY_NAME] = entry;
    return base;
}

/**
 * Return the Antigravity hooks configuration without the claude-dev-env entry.
 *
 * @param {object} configuration Parsed ~/.gemini/config/hooks.json object.
 * @returns {object} Updated configuration object.
 */
export function withoutAntigravityHooks(configuration) {
    if (!configuration || typeof configuration !== 'object' || Array.isArray(configuration)) {
        return {};
    }
    const { [ANTIGRAVITY_HOOKS_ENTRY_NAME]: _removed, ...rest } = configuration;
    return rest;
}

/**
 * Register the claude-dev-env lifecycle hook bridge in ~/.gemini/config/hooks.json.
 *
 * @param {{antigravityConfigDirectory: string, scriptsDirectory: string, claudeHomeDirectory: string, pythonCommand?: string, formatPathArgument?: (pathValue: string) => string}} options Install paths and interpreter.
 * @returns {string|null} The hooks.json path when this run changed it.
 */
export function writeAntigravityHooks(options) {
    const hooksPath = join(options.antigravityConfigDirectory, ANTIGRAVITY_HOOKS_FILE_NAME);
    const currentText = existsSync(hooksPath) ? readFileSync(hooksPath, 'utf8') : null;
    const current = currentText === null ? {} : JSON.parse(currentText.replace(/^\uFEFF/, ''));
    const entry = buildAntigravityHookEntry(options);
    const updatedText = `${JSON.stringify(mergeAntigravityHooks(current, entry), null, 2)}\n`;
    if (updatedText === currentText) return null;
    mkdirSync(options.antigravityConfigDirectory, { recursive: true });
    writeFileSync(hooksPath, updatedText);
    return hooksPath;
}

/**
 * Remove the claude-dev-env hook entry from ~/.gemini/config/hooks.json when present.
 *
 * @param {string} antigravityConfigDirectory The ~/.gemini/config directory.
 * @returns {string|null} The hooks.json path when this run changed it.
 */
export function removeAntigravityHooks(antigravityConfigDirectory) {
    const hooksPath = join(antigravityConfigDirectory, ANTIGRAVITY_HOOKS_FILE_NAME);
    if (!existsSync(hooksPath)) return null;
    const currentText = readFileSync(hooksPath, 'utf8');
    const current = JSON.parse(currentText.replace(/^\uFEFF/, ''));
    if (!(ANTIGRAVITY_HOOKS_ENTRY_NAME in current)) return null;
    const updatedText = `${JSON.stringify(withoutAntigravityHooks(current), null, 2)}\n`;
    if (updatedText === currentText) return null;
    writeFileSync(hooksPath, updatedText);
    return hooksPath;
}
