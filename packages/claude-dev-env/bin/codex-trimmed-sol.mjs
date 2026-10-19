import { lstatSync, mkdirSync, readFileSync, realpathSync, rmSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

import { DEFAULT_CODEX_DIRECTORY_NAME } from './install-constants.mjs';

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

function isPackageMarkerLine(eachLine) {
    return eachLine.replace(/\r$/, '') === SOL_SETTING_MARKER;
}

function withoutPackageSetting(allLines) {
    const allKeptLines = [];
    for (let i = 0; i < allLines.length; i++) {
        if (isPackageMarkerLine(allLines[i])) {
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

/**
 * Return the Codex home whose folder holds the prompt the config.toml setting names.
 *
 * Account sync links each account home's config.toml to the main Codex
 * home's file: a symbolic link, or a hard link when the account cannot
 * create one. Every home that shares that file shares one setting, so the
 * prompt it names belongs in the main home. Any other home uses its own
 * folder, including a home whose config.toml links into a dotfiles folder.
 *
 * @param {string} codexHome
 * @returns {string}
 */
export function codexConfigDirectory(codexHome) {
    const mainCodexHome = join(homedir(), DEFAULT_CODEX_DIRECTORY_NAME);
    const sharesMainConfig = isSameFile(
        join(codexHome, CODEX_CONFIG_FILE_NAME),
        join(mainCodexHome, CODEX_CONFIG_FILE_NAME),
    );
    return sharesMainConfig ? mainCodexHome : codexHome;
}

function isSameFile(firstPath, secondPath) {
    try {
        const firstEntry = statSync(firstPath, { bigint: true, throwIfNoEntry: false });
        const secondEntry = statSync(secondPath, { bigint: true, throwIfNoEntry: false });
        return Boolean(firstEntry && secondEntry && firstEntry.dev === secondEntry.dev && firstEntry.ino === secondEntry.ino);
    } catch {
        return false;
    }
}

/**
 * True when CODEX_HOME is an account home whose config.toml is the main Codex home's file.
 *
 * Such a home borrows the setting and the prompt from the main home, so
 * uninstalling from it leaves both alone.
 *
 * @param {string} codexHome
 * @returns {boolean}
 */
export function codexConfigIsBorrowed(codexHome) {
    if (!lstatSync(join(codexHome, CODEX_CONFIG_FILE_NAME), { throwIfNoEntry: false })) return false;
    return realpathOrSelf(codexConfigDirectory(codexHome)) !== realpathOrSelf(codexHome);
}

function realpathOrSelf(path) {
    try {
        return realpathSync(path);
    } catch {
        return path;
    }
}

/**
 * Return where the installer keeps the Codex copy of the trimmed Sol prompt.
 *
 * The copy sits in CODEX_HOME, or in the main Codex home when CODEX_HOME is
 * an account home that shares its config.toml, so the file the setting names
 * stays put when any claude-dev-env version, older ones included, prunes or
 * rewrites the managed files under ~/.claude, and every home that shares that
 * config.toml names the same copy. A missing file makes every Codex command
 * fail before it starts.
 *
 * @param {string} codexHome
 * @returns {string}
 */
export function codexSolPromptPath(codexHome) {
    return join(codexConfigDirectory(codexHome), SOL_PROMPT_FILE_NAME);
}

/**
 * Copy the trimmed Sol prompt to the folder `codexSolPromptPath` names.
 *
 * An account home that shares the main config.toml also loses the copy an earlier
 * install left in its own folder, since no setting names that copy any more.
 *
 * @param {string} codexHome
 * @param {string} sourcePromptPath The prompt file the package ships.
 * @returns {string|null} The prompt copy's path when this call wrote it, and null when it was already current.
 */
export function installCodexSolPrompt(codexHome, sourcePromptPath) {
    if (codexConfigIsBorrowed(codexHome)) rmSync(join(codexHome, SOL_PROMPT_FILE_NAME), { force: true });
    const promptPath = codexSolPromptPath(codexHome);
    const promptText = readFileSync(sourcePromptPath, 'utf8');
    const promptEntry = lstatSync(promptPath, { throwIfNoEntry: false });
    if (promptEntry?.isFile() && readFileSync(promptPath, 'utf8') === promptText) return null;
    mkdirSync(dirname(promptPath), { recursive: true });
    writeFileSync(promptPath, promptText, 'utf8');
    return promptPath;
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
 * package line is removed. The prompt copy is removed in every case, because
 * install writes it even when the user's own setting kept the package line
 * out. An account home that shares the main config.toml only drops its own
 * leftover copy: the shared setting and prompt belong to the main home, and
 * other homes still read them.
 *
 * @param {string} codexHome
 * @returns {string|null} The config path when it changed, or null when nothing was removed.
 */
export function removeCodexSolSetting(codexHome) {
    if (codexConfigIsBorrowed(codexHome)) {
        rmSync(join(codexHome, SOL_PROMPT_FILE_NAME), { force: true });
        return null;
    }
    rmSync(codexSolPromptPath(codexHome), { force: true });
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    if (!isReadable || currentText === null) return null;
    const allLines = currentText.split('\n');
    if (!allLines.some(isPackageMarkerLine)) return null;
    const userText = withoutPackageSetting(allLines).join('\n');
    if (userText.trim() === '') {
        unlinkSync(configPath);
    } else {
        writeFileSync(configPath, userText, 'utf8');
    }
    return configPath;
}
