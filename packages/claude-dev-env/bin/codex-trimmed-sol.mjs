import { existsSync, lstatSync, mkdirSync, readFileSync, rmSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';

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
    return sharesMainConfig(codexHome, mainCodexHome) ? mainCodexHome : codexHome;
}

export function sharesMainConfig(codexHome, mainCodexHome) {
    return isSameFile(join(codexHome, CODEX_CONFIG_FILE_NAME), join(mainCodexHome, CODEX_CONFIG_FILE_NAME));
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
 * uninstalling from it leaves both alone. The homes are compared as folders
 * on disk, so a CODEX_HOME spelled with other letter case or through a link
 * still counts as the main home.
 *
 * @param {string} codexHome
 * @returns {boolean}
 */
export function codexConfigIsBorrowed(codexHome) {
    const mainCodexHome = join(homedir(), DEFAULT_CODEX_DIRECTORY_NAME);
    return sharesMainConfig(codexHome, mainCodexHome) && !isSameFile(codexHome, mainCodexHome);
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

function isInstallRoot(codexHome) {
    const mainHome = join(homedir(), DEFAULT_CODEX_DIRECTORY_NAME);
    if (sameDirectory(codexHome, mainHome)) return true;
    const named = process.env.CODEX_HOME;
    return typeof named === 'string' && named.trim() !== '' && sameDirectory(codexHome, named.trim());
}

export function codexSolSettingSnapshotPaths(codexHome) {
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    const paths = isReadable && currentText !== null ? [configPath] : [];
    if (!isInstallRoot(codexHome)) return paths;
    for (const eachHome of codexSolHomes(codexHome)) {
        if (sameDirectory(eachHome, codexHome)) continue;
        const eachConfigPath = join(eachHome, CODEX_CONFIG_FILE_NAME);
        const eachConfig = readCodexConfig(eachConfigPath);
        if (eachConfig.isReadable && eachConfig.currentText !== null) paths.push(eachConfigPath);
        paths.push(join(eachHome, SOL_PROMPT_FILE_NAME));
    }
    return [...new Set(paths)];
}

const CODEX_PROFILES_DIRECTORY_NAME = '.codex-profiles';
const CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE = 'CODEX_PROFILES_ROOT';
const CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE = 'CODEX_ACCOUNT_PROFILES';
const CODEX_ACCOUNT_LAUNCHERS_FILE_NAME = 'account-launchers.json';
const DEFAULT_CODEX_ACCOUNT_NAMES = ['codex-1', 'codex-2', 'codex-3', 'codex-4'];

function foldPath(filePath) {
    const resolved = resolve(filePath);
    return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}

function sameDirectory(firstPath, secondPath) {
    return foldPath(firstPath) === foldPath(secondPath);
}

function isExistingFile(filePath) {
    try {
        return statSync(filePath, { throwIfNoEntry: false })?.isFile() === true;
    } catch {
        return false;
    }
}

function isUnderTempDirectory(filePath) {
    const rootKey = foldPath(tmpdir());
    const pathKey = foldPath(filePath);
    const prefix = rootKey.endsWith(sep) ? rootKey : `${rootKey}${sep}`;
    return pathKey === rootKey || pathKey.startsWith(prefix);
}

function parseInstructionsTarget(line) {
    const match = line.replace(/\r$/, '').match(/^\s*model_instructions_file\s*=\s*(.*)$/);
    if (!match) return null;
    const raw = match[1].trim();
    if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
        try {
            const parsed = JSON.parse(raw);
            return typeof parsed === 'string' ? parsed : null;
        } catch {
            return null;
        }
    }
    if (raw.length >= 2 && raw.startsWith("'") && raw.endsWith("'")) {
        return raw.slice(1, -1);
    }
    return null;
}

function instructionsNeedReplacement(line) {
    const targetPath = parseInstructionsTarget(line);
    if (targetPath === null) return false;
    if (targetPath === '') return true;
    if (isUnderTempDirectory(targetPath)) return true;
    return !isExistingFile(targetPath);
}

function instructionLineIndexes(allLines) {
    for (let index = 0; index < allLines.length; index += 1) {
        const stripped = allLines[index].replace(/\r$/, '');
        if (TABLE_HEADER_PATTERN.test(stripped)) return null;
        if (isPackageMarkerLine(allLines[index])) {
            const nextIndex = index + 1;
            if (nextIndex < allLines.length && INSTRUCTIONS_KEY_PATTERN.test(allLines[nextIndex])) {
                return { markerIndex: index, lineIndex: nextIndex };
            }
            continue;
        }
        if (INSTRUCTIONS_KEY_PATTERN.test(stripped)) {
            return { markerIndex: null, lineIndex: index };
        }
    }
    return null;
}

function homeDirectoryFrom(environment) {
    const named = environment.HOME || environment.USERPROFILE;
    if (typeof named === 'string' && named.trim()) return resolve(named.trim());
    return homedir();
}

function profilesRootFrom(environment, homeDirectory) {
    const named = environment[CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE];
    if (typeof named === 'string' && named.trim()) return resolve(named.trim());
    return join(homeDirectory, CODEX_PROFILES_DIRECTORY_NAME);
}

function accountNamesFrom(profilesRoot, environment) {
    const named = environment[CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE];
    if (typeof named === 'string' && named.trim()) {
        return named.split(',').map((eachName) => eachName.trim()).filter(Boolean);
    }
    const rosterPath = join(profilesRoot, CODEX_ACCOUNT_LAUNCHERS_FILE_NAME);
    if (!lstatSync(rosterPath, { throwIfNoEntry: false })?.isFile()) return DEFAULT_CODEX_ACCOUNT_NAMES;
    try {
        const parsed = JSON.parse(readFileSync(rosterPath, 'utf8'));
        if (Array.isArray(parsed) && parsed.every((eachName) => typeof eachName === 'string')) {
            return parsed.map((eachName) => eachName.trim()).filter(Boolean);
        }
    } catch {
        return [];
    }
    return [];
}

/**
 * Homes whose `config.toml` can hold its own Sol prompt line.
 *
 * The main Codex home is always included. `CODEX_HOME` is included when its
 * `config.toml` is not the main file. Each account home under the profiles
 * root is included when that home already has a `config.toml` and
 * `sharesMainConfig` says it is not the main file. Account sync in
 * `scripts/codex_account_choice.py` is what links the shared ones.
 *
 * @param {string} codexHome
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {string[]}
 */
export function codexSolHomes(codexHome, environment = process.env) {
    const homeDirectory = homeDirectoryFrom(environment);
    const mainHome = join(homeDirectory, DEFAULT_CODEX_DIRECTORY_NAME);
    const homes = [mainHome];
    if (!sameDirectory(codexHome, mainHome) && !sharesMainConfig(codexHome, mainHome)) {
        homes.push(codexHome);
    }
    const profilesRoot = profilesRootFrom(environment, homeDirectory);
    for (const eachName of accountNamesFrom(profilesRoot, environment)) {
        const accountHome = join(profilesRoot, eachName);
        if (homes.some((eachHome) => sameDirectory(eachHome, accountHome))) continue;
        if (!existsSync(join(accountHome, CODEX_CONFIG_FILE_NAME))) continue;
        if (sharesMainConfig(accountHome, mainHome)) continue;
        homes.push(accountHome);
    }
    return homes;
}

/**
 * Point CODEX_HOME/config.toml's `model_instructions_file` at the installed Sol prompt.
 *
 * The package line sits at the top of the file, before any table, so it is a
 * top-level key. A top-level line whose target exists and sits outside the
 * temp directory stays, with or without the package marker. A top-level line
 * whose target is missing or under the temp directory is replaced with
 * `instructionsPath`. A directory at the config path stays as it is.
 * Called with the durable prompt path on the install root, this also writes
 * that prompt and setting for each other home `codexSolHomes` names. The
 * installer calls it that way, so account homes are covered without a second
 * installer entry.
 *
 * @param {string} codexHome
 * @param {string} instructionsPath Absolute path of the installed prompt file.
 * @returns {string|null} The config path when this home's file changed, and null otherwise.
 */
function writeOneCodexSolSetting(codexHome, instructionsPath) {
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const { isReadable, currentText } = readCodexConfig(configPath);
    if (!isReadable) return null;
    const allLines = (currentText ?? '').split('\n');
    const found = instructionLineIndexes(allLines);
    let userLines = allLines;
    if (found) {
        if (!instructionsNeedReplacement(allLines[found.lineIndex])) return null;
        userLines = allLines.filter((unusedLine, index) => index !== found.lineIndex && index !== found.markerIndex);
    }
    const userText = userLines.join('\n');
    const configText = [...solSettingLines(instructionsPath), userText === '' ? '' : userText].join('\n');
    if (currentText === configText) return null;
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, configText, 'utf8');
    return configPath;
}

export function writeCodexSolSetting(codexHome, instructionsPath) {
    const changed = writeOneCodexSolSetting(codexHome, instructionsPath);
    if (instructionsPath !== codexSolPromptPath(codexHome) || !isInstallRoot(codexHome)) return changed;
    if (!isExistingFile(instructionsPath)) return changed;
    for (const eachHome of codexSolHomes(codexHome)) {
        if (sameDirectory(eachHome, codexHome)) continue;
        installCodexSolPrompt(eachHome, instructionsPath);
        writeOneCodexSolSetting(eachHome, codexSolPromptPath(eachHome));
    }
    return changed;
}

/**
 * Install the Sol prompt and write its setting for every home `codexSolHomes` names.
 *
 * A borrowed account home still drops a leftover prompt copy in its own folder.
 * Running this twice leaves the files as the first run wrote them.
 *
 * @param {string} codexHome
 * @param {string} sourcePromptPath The prompt file the package ships.
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {string[]} Paths this call wrote.
 */
export function applyCodexSolSettings(codexHome, sourcePromptPath, environment = process.env) {
    const changed = [];
    for (const eachHome of codexSolHomes(codexHome, environment)) {
        const promptPath = installCodexSolPrompt(eachHome, sourcePromptPath);
        const settingPath = writeCodexSolSetting(eachHome, codexSolPromptPath(eachHome));
        if (promptPath) changed.push(promptPath);
        if (settingPath) changed.push(settingPath);
    }
    if (codexConfigIsBorrowed(codexHome)) installCodexSolPrompt(codexHome, sourcePromptPath);
    return changed;
}

/**
 * Paths the install transaction must remember before the Sol prompt write.
 *
 * @param {string} codexHome
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {string[]}
 */
export function codexSolSnapshotPaths(codexHome, environment = process.env) {
    const paths = [];
    for (const eachHome of codexSolHomes(codexHome, environment)) {
        paths.push(...codexSolSettingSnapshotPaths(eachHome));
        paths.push(codexSolPromptPath(eachHome));
        paths.push(join(eachHome, SOL_PROMPT_FILE_NAME));
    }
    if (codexConfigIsBorrowed(codexHome)) {
        paths.push(...codexSolSettingSnapshotPaths(codexHome));
        paths.push(join(codexHome, SOL_PROMPT_FILE_NAME));
    }
    return [...new Set(paths)];
}

/**
 * Remove the package Sol line from every home an install would have written.
 *
 * Uninstall from an account home that shares the main `config.toml` leaves
 * that shared file alone and only drops the account folder's leftover copy.
 *
 * @param {string} codexHome
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {string[]} Config paths this call changed.
 */
export function removeCodexSolSettings(codexHome, environment = process.env) {
    const homes = codexConfigIsBorrowed(codexHome) ? [codexHome] : codexSolHomes(codexHome, environment);
    const changed = [];
    for (const eachHome of homes) {
        const configPath = removeCodexSolSetting(eachHome);
        if (configPath) changed.push(configPath);
    }
    return changed;
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
function removeOneCodexSolSetting(codexHome) {
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

export function removeCodexSolSetting(codexHome) {
    if (codexConfigIsBorrowed(codexHome)) {
        rmSync(join(codexHome, SOL_PROMPT_FILE_NAME), { force: true });
        return null;
    }
    const changed = removeOneCodexSolSetting(codexHome);
    if (!isInstallRoot(codexHome)) return changed;
    for (const eachHome of codexSolHomes(codexHome)) {
        if (sameDirectory(eachHome, codexHome) || codexConfigIsBorrowed(eachHome)) continue;
        removeOneCodexSolSetting(eachHome);
    }
    return changed;
}
