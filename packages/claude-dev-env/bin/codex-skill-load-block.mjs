import { lstatSync, mkdirSync, readFileSync, readlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

export const SKILL_LOAD_BLOCK_START = '<!-- claude-dev-env skill load: start -->';
export const SKILL_LOAD_BLOCK_END = '<!-- claude-dev-env skill load: end -->';
export const SKILL_LOAD_INSTRUCTION = 'Load the pstack:poteto-mode skill before your first tool call or reply: '
    + 'open its SKILL.md from your skills list and follow it. This binds every Codex agent, '
    + 'including a helper started with spawn_agent, whatever its task message says.';
export const PACKAGE_GUIDANCE_BLOCK_START = '<!-- claude-dev-env package guidance: start -->';
export const PACKAGE_GUIDANCE_BLOCK_END = '<!-- claude-dev-env package guidance: end -->';
export const QUESTION_PRESENTATION_BLOCK_START = '<!-- claude-dev-env question presentation: start -->';
export const QUESTION_PRESENTATION_BLOCK_END = '<!-- claude-dev-env question presentation: end -->';

const WINDOWS_LONG_PATH_PREFIX = '\\\\?\\';

function managedBlock(blockStart, blockBody, blockEnd) {
    const terminatedBody = blockBody.endsWith('\n') ? blockBody : `${blockBody}\n`;
    return `${blockStart}\n${terminatedBody}${blockEnd}\n`;
}

function withBlockReplaced(guidanceText, blockStart, blockEnd, block) {
    const firstStartIndex = guidanceText.indexOf(blockStart);
    const endIndex = firstStartIndex === -1 ? -1 : guidanceText.indexOf(blockEnd, firstStartIndex);
    if (endIndex === -1) return null;
    const startIndex = guidanceText.lastIndexOf(blockStart, endIndex);
    let afterBlockIndex = endIndex + blockEnd.length;
    if (guidanceText[afterBlockIndex] === '\n') afterBlockIndex += 1;
    return guidanceText.slice(0, startIndex) + block + guidanceText.slice(afterBlockIndex);
}

/**
 * Return the Codex guidance text with the package's skill-load block in it.
 *
 * Codex starts a spawn_agent helper without running any hook, so the global
 * AGENTS.md is the one channel that reaches every helper. A block already in
 * the text is replaced where it stands; otherwise the block goes first.
 */
export function withSkillLoadBlock(guidanceText) {
    const block = managedBlock(SKILL_LOAD_BLOCK_START, SKILL_LOAD_INSTRUCTION, SKILL_LOAD_BLOCK_END);
    const replacedText = withBlockReplaced(guidanceText, SKILL_LOAD_BLOCK_START, SKILL_LOAD_BLOCK_END, block);
    if (replacedText !== null) return replacedText;
    return guidanceText ? `${block}\n${guidanceText}` : block;
}

function withPackageGuidanceBlock(guidanceText, packageGuidanceText) {
    const block = managedBlock(PACKAGE_GUIDANCE_BLOCK_START, packageGuidanceText, PACKAGE_GUIDANCE_BLOCK_END);
    const replacedText = withBlockReplaced(
        guidanceText,
        PACKAGE_GUIDANCE_BLOCK_START,
        PACKAGE_GUIDANCE_BLOCK_END,
        block,
    );
    if (replacedText !== null) return replacedText;
    return guidanceText ? `${guidanceText}\n${block}` : block;
}

function comparablePath(filePath) {
    const withoutPrefix = filePath.startsWith(WINDOWS_LONG_PATH_PREFIX)
        ? filePath.slice(WINDOWS_LONG_PATH_PREFIX.length)
        : filePath;
    const resolvedPath = resolve(withoutPrefix);
    return process.platform === 'win32' ? resolvedPath.toLowerCase() : resolvedPath;
}

function linksToPackageGuidance(agentsPath, allPackageGuidancePaths) {
    const linkTarget = comparablePath(resolve(dirname(agentsPath), readlinkSync(agentsPath)));
    return allPackageGuidancePaths.some(eachPath => comparablePath(eachPath) === linkTarget);
}

function writeCodexGuidanceFile(codexHome, allPackageGuidancePaths, transformGuidance) {
    const agentsPath = join(codexHome, 'AGENTS.md');
    const agentsEntry = lstatSync(agentsPath, { throwIfNoEntry: false });
    if (agentsEntry && !agentsEntry.isFile() && !agentsEntry.isSymbolicLink()) return null;
    const isPackageGuidanceLink = agentsEntry?.isSymbolicLink() ?? false;
    if (isPackageGuidanceLink && !linksToPackageGuidance(agentsPath, allPackageGuidancePaths)) return null;
    const currentText = agentsEntry && !isPackageGuidanceLink ? readFileSync(agentsPath, 'utf8') : '';
    const updatedText = transformGuidance(currentText);
    if (!isPackageGuidanceLink && updatedText === currentText) return null;
    mkdirSync(codexHome, { recursive: true });
    if (isPackageGuidanceLink) unlinkSync(agentsPath);
    writeFileSync(agentsPath, updatedText, 'utf8');
    return agentsPath;
}

/**
 * Keep CODEX_HOME/AGENTS.md carrying the skill-load block and the package guidance.
 *
 * The skill-load block goes first, and the package-guidance block holds the
 * current guidance text. A symbolic link that points at the package guidance
 * (the shared agents-home copy, or the retired copy under the Claude home) is
 * replaced by a regular file holding both blocks, so Codex keeps both after
 * the package moves its guidance. A link to any other file is left alone.
 *
 * Returns the file path when the file changed, and null otherwise.
 */
export function writeCodexAgentsGuidance(codexHome, packageGuidanceText, allPackageGuidancePaths) {
    return writeCodexGuidanceFile(
        codexHome,
        allPackageGuidancePaths,
        currentText => withPackageGuidanceBlock(withSkillLoadBlock(currentText), packageGuidanceText),
    );
}

/**
 * Keep CODEX_HOME/AGENTS.md carrying the package guidance, with no skill-load block.
 *
 * Links follow the same rule as writeCodexAgentsGuidance. Returns the file
 * path when the file changed, and null otherwise.
 */
export function writeCodexPackageGuidance(codexHome, packageGuidanceText, allPackageGuidancePaths) {
    return writeCodexGuidanceFile(
        codexHome,
        allPackageGuidancePaths,
        currentText => withPackageGuidanceBlock(currentText, packageGuidanceText),
    );
}

export function writeCodexQuestionGuidance(codexHome, policyText) {
    const agentsPath = join(codexHome, 'AGENTS.md');
    const agentsEntry = lstatSync(agentsPath, { throwIfNoEntry: false });
    if (agentsEntry && !agentsEntry.isFile()) return null;
    const currentText = agentsEntry ? readFileSync(agentsPath, 'utf8') : '';
    const block = managedBlock(QUESTION_PRESENTATION_BLOCK_START, policyText, QUESTION_PRESENTATION_BLOCK_END);
    const replacedText = withBlockReplaced(
        currentText, QUESTION_PRESENTATION_BLOCK_START, QUESTION_PRESENTATION_BLOCK_END, block,
    );
    const separator = currentText && !currentText.endsWith('\n') ? '\n\n' : currentText ? '\n' : '';
    const updatedText = replacedText ?? `${currentText}${separator}${block}`;
    if (updatedText === currentText) return null;
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(agentsPath, updatedText, 'utf8');
    return agentsPath;
}

const ALL_PACKAGE_MANAGED_BLOCK_MARKERS = [
    [SKILL_LOAD_BLOCK_START, SKILL_LOAD_BLOCK_END],
    [PACKAGE_GUIDANCE_BLOCK_START, PACKAGE_GUIDANCE_BLOCK_END],
    [QUESTION_PRESENTATION_BLOCK_START, QUESTION_PRESENTATION_BLOCK_END],
];

/**
 * Report whether the guidance holds at least one package-managed block and
 * nothing else but blank lines.
 */
export function hasOnlyPackageManagedBlocks(guidanceText) {
    let remainingText = guidanceText;
    let removedBlockCount = 0;
    for (const [blockStart, blockEnd] of ALL_PACKAGE_MANAGED_BLOCK_MARKERS) {
        const withoutBlock = withBlockReplaced(remainingText, blockStart, blockEnd, '');
        if (withoutBlock === null) continue;
        remainingText = withoutBlock;
        removedBlockCount += 1;
    }
    return removedBlockCount > 0 && remainingText.trim() === '';
}

function removeCodexGuidanceBlock(codexHome, blockStart, blockEnd) {
    const agentsPath = join(codexHome, 'AGENTS.md');
    const agentsEntry = lstatSync(agentsPath, { throwIfNoEntry: false });
    if (!agentsEntry?.isFile()) return null;
    const currentText = readFileSync(agentsPath, 'utf8');
    const updatedText = withBlockReplaced(currentText, blockStart, blockEnd, '');
    if (updatedText === null) return null;
    const isLeftEmpty = updatedText.trim() === '';
    if (isLeftEmpty) unlinkSync(agentsPath);
    if (!isLeftEmpty) writeFileSync(agentsPath, updatedText, 'utf8');
    return agentsPath;
}

/**
 * Remove the managed question block while keeping surrounding guidance bytes.
 *
 * A file left holding only blank lines is deleted.
 *
 * @param {string} codexHome
 * @returns {string|null} The changed path, or null when no block was removed.
 */
export function removeCodexQuestionGuidance(codexHome) {
    return removeCodexGuidanceBlock(
        codexHome, QUESTION_PRESENTATION_BLOCK_START, QUESTION_PRESENTATION_BLOCK_END,
    );
}

/**
 * Remove the managed package-guidance block while keeping surrounding guidance bytes.
 *
 * A file left holding only blank lines is deleted.
 *
 * @param {string} codexHome
 * @returns {string|null} The changed path, or null when no block was removed.
 */
export function removeCodexPackageGuidance(codexHome) {
    return removeCodexGuidanceBlock(codexHome, PACKAGE_GUIDANCE_BLOCK_START, PACKAGE_GUIDANCE_BLOCK_END);
}
