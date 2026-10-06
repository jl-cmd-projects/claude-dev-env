import { lstatSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const SOL_PROFILE_NAME = 'trimmed-sol';
export const SOL_PROFILE_MODEL = 'gpt-6.1-sol';
export const SOL_PROMPT_DIRECTORY_NAME = 'system-prompts';
export const SOL_PROMPT_FILE_NAME = 'codex-sol.md';
export const SOL_PROFILE_FILE_NAME = `${SOL_PROFILE_NAME}.config.toml`;
export const SOL_PROFILE_HEADER = '# claude-dev-env trimmed Sol profile. A claude-dev-env install rewrites this file.';

/**
 * Return the Codex profile file text that runs Sol on the trimmed prompt.
 *
 * Codex reads `CODEX_HOME/<name>.config.toml` when a run passes
 * `--profile <name>`, and `model_instructions_file` replaces the model's
 * default prompt with the file it names. JSON string escaping is valid
 * TOML basic-string escaping, so a Windows path keeps its backslashes.
 *
 * @param {string} instructionsPath Absolute path of the installed prompt file.
 * @returns {string}
 */
export function solProfileContent(instructionsPath) {
    return [
        SOL_PROFILE_HEADER,
        `model = ${JSON.stringify(SOL_PROFILE_MODEL)}`,
        `model_instructions_file = ${JSON.stringify(instructionsPath)}`,
        '',
    ].join('\n');
}

function readPackageProfile(profilePath) {
    const profileEntry = lstatSync(profilePath, { throwIfNoEntry: false });
    if (!profileEntry) return { isWritable: true, currentText: null };
    if (!profileEntry.isFile()) return { isWritable: false, currentText: null };
    const currentText = readFileSync(profilePath, 'utf8');
    return { isWritable: currentText.startsWith(SOL_PROFILE_HEADER), currentText };
}

/**
 * Keep CODEX_HOME/trimmed-sol.config.toml pointing at the installed Sol prompt.
 *
 * A file without the package header belongs to the user and stays as it is,
 * and so does any entry that is not a regular file.
 *
 * @param {string} codexHome
 * @param {string} instructionsPath Absolute path of the installed prompt file.
 * @returns {string|null} The profile path when the file changed, and null otherwise.
 */
export function writeCodexSolProfile(codexHome, instructionsPath) {
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const { isWritable, currentText } = readPackageProfile(profilePath);
    const profileText = solProfileContent(instructionsPath);
    if (!isWritable || currentText === profileText) return null;
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(profilePath, profileText, 'utf8');
    return profilePath;
}

/**
 * Remove the package's Sol profile file, leaving a user-owned file in place.
 *
 * @param {string} codexHome
 * @returns {string|null} The removed path, or null when nothing was removed.
 */
export function removeCodexSolProfile(codexHome) {
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const { isWritable, currentText } = readPackageProfile(profilePath);
    if (!isWritable || currentText === null) return null;
    unlinkSync(profilePath);
    return profilePath;
}
