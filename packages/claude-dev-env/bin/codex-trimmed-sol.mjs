import { lstatSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const SOL_PROMPT_DIRECTORY_NAME = 'system-prompts';
export const SOL_PROMPT_FILE_NAME = 'codex-sol.md';
export const CODEX_CONFIG_FILE_NAME = 'config.toml';
export const SOL_SETTING_MARKER = '# claude-dev-env trimmed Sol prompt. A claude-dev-env install rewrites the next line.';
const INSTRUCTIONS_KEY_PATTERN = /^\s*model_instructions_file\s*=/;
const TABLE_HEADER_PATTERN = /^\s*\[/;

/**
 * Return the two config.toml lines that point Codex at the trimmed prompt.
 *
 * `model_instructions_file` replaces the selected model's built-in prompt with
 * the file it names, for every model a run selects. JSON string escaping is
 * valid TOML basic-string escaping, so a Windows path keeps its backslashes.
 *
 * @param {string} instructionsPath Absolute path of the installed prompt file.
 * @returns {string[]}
 */
export function solSettingLines(instructionsPath) {
    return [SOL_SETTING_MARKER, `model_instructions_file = ${JSON.stringify(instructionsPath)}`];
}

function withoutPackageSetting(allLines) {
    const allKeptLines = [];
    for (let i = 0; i < allLines.length; i++) {
        if (allLines[i] === SOL_SETTING_MARKER) {
            i++;
            continue;
        }
        allKeptLines.push(allLines[i]);
    }
    return allKeptLines;
}

function hasUserInstructionsSetting(allLines) {
    for (const eachLine of allLines) {
        if (TABLE_HEADER_PATTERN.test(eachLine)) return false;
        if (INSTRUCTIONS_KEY_PATTERN.test(eachLine)) return true;
    }
    return false;
}

function readCodexConfig(configPath) {
    const configEntry = lstatSync(configPath, { throwIfNoEntry: false });
    if (!configEntry) return { isReadable: true, currentText: null };
    if (configEntry.isDirectory()) return { isReadable: false, currentText: null };
    return { isReadable: true, currentText: readFileSync(configPath, 'utf8') };
}

export function codexSolSettingSnapshotPaths(codexHome) {
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    return isReadable && currentText !== null ? [configPath] : [];
}

/**
 * Point CODEX_HOME/config.toml's `model_instructions_file` at the installed Sol prompt.
 *
 * The package line sits at the top of the file, before any table, so it is a
 * top-level key. A top-level `model_instructions_file` the user wrote keeps
 * the file as it is, and so does a directory at the config path.
 *
 * @param {string} codexHome
 * @param {string} instructionsPath Absolute path of the installed prompt file.
 * @returns {string|null} The config path when the file changed, and null otherwise.
 */
export function writeCodexSolSetting(codexHome, instructionsPath) {
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    if (!isReadable) return null;
    const allUserLines = withoutPackageSetting((currentText ?? '').split('\n'));
    if (hasUserInstructionsSetting(allUserLines)) return null;
    const userText = allUserLines.join('\n');
    const configText = [...solSettingLines(instructionsPath), userText === '' ? '' : userText].join('\n');
    if (currentText === configText) return null;
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, configText, 'utf8');
    return configPath;
}

/**
 * Remove the package's `model_instructions_file` line from CODEX_HOME/config.toml.
 *
 * The rest of the file stays as the user wrote it. A file that held only the
 * package line is removed.
 *
 * @param {string} codexHome
 * @returns {string|null} The config path when it changed, or null when nothing was removed.
 */
export function removeCodexSolSetting(codexHome) {
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    if (!isReadable || currentText === null) return null;
    const allLines = currentText.split('\n');
    if (!allLines.includes(SOL_SETTING_MARKER)) return null;
    const userText = withoutPackageSetting(allLines).join('\n');
    if (userText.trim() === '') {
        unlinkSync(configPath);
    } else {
        writeFileSync(configPath, userText, 'utf8');
    }
    return configPath;
}
