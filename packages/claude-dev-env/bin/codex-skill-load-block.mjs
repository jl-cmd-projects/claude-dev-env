import { lstatSync, mkdirSync, readFileSync, readlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

export const SKILL_LOAD_BLOCK_START = '<!-- claude-dev-env skill load: start -->';
export const SKILL_LOAD_BLOCK_END = '<!-- claude-dev-env skill load: end -->';
export const PACKAGE_GUIDANCE_BLOCK_START = '<!-- claude-dev-env package guidance: start -->';
export const PACKAGE_GUIDANCE_BLOCK_END = '<!-- claude-dev-env package guidance: end -->';
export const QUESTION_PRESENTATION_BLOCK_START = '<!-- claude-dev-env question presentation: start -->';
export const QUESTION_PRESENTATION_BLOCK_END = '<!-- claude-dev-env question presentation: end -->';
export const DEEPEN_GUIDANCE_BLOCK_START = '<!-- claude-dev-env deepen: start -->';
export const DEEPEN_GUIDANCE_BLOCK_END = '<!-- claude-dev-env deepen: end -->';

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
 * Return guidance text with every complete skill-load block removed.
 *
 * When a block is the start of the remaining text, one following blank line is
 * removed with it. A start marker with no end marker stays.
 */
export function withoutSkillLoadBlock(guidanceText) {
    let remainingText = guidanceText;
    let removedBlockCount = 0;
    while (remainingText.includes(SKILL_LOAD_BLOCK_START)) {
        const blockStartsAtTop = remainingText.startsWith(SKILL_LOAD_BLOCK_START);
        const replacedText = withBlockReplaced(remainingText, SKILL_LOAD_BLOCK_START, SKILL_LOAD_BLOCK_END, '');
        if (replacedText === null || replacedText === remainingText) break;
        removedBlockCount += 1;
        remainingText = blockStartsAtTop && replacedText.startsWith('\n')
            ? replacedText.slice(1)
            : replacedText;
    }
    return removedBlockCount === 0 ? guidanceText : remainingText;
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
    const updatedText = transformGuidance(withoutSkillLoadBlock(currentText));
    if (!isPackageGuidanceLink && updatedText === currentText) return null;
    mkdirSync(codexHome, { recursive: true });
    if (isPackageGuidanceLink) unlinkSync(agentsPath);
    writeFileSync(agentsPath, updatedText, 'utf8');
    return agentsPath;
}

/**
 * Remove a skill-load block and write package guidance into CODEX_HOME/AGENTS.md.
 *
 * Link handling matches writeCodexPackageGuidance. Returns the file path when
 * the file changed, and null otherwise.
 */
export function writeCodexAgentsGuidance(codexHome, packageGuidanceText, allPackageGuidancePaths) {
    return writeCodexPackageGuidance(codexHome, packageGuidanceText, allPackageGuidancePaths);
}

/**
 * Keep CODEX_HOME/AGENTS.md carrying the package guidance, with no skill-load block.
 *
 * An existing skill-load block is removed. A symbolic link that points at the
 * package guidance, the shared agents-home copy or the retired copy under the
 * Claude home, is replaced by a regular file. A link to any other file is left
 * alone.
 *
 * Returns the file path when the file changed, and null otherwise.
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
    [DEEPEN_GUIDANCE_BLOCK_START, DEEPEN_GUIDANCE_BLOCK_END],
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

export function removeCodexDeepenGuidance(codexHome) {
    return removeCodexGuidanceBlock(codexHome, DEEPEN_GUIDANCE_BLOCK_START, DEEPEN_GUIDANCE_BLOCK_END);
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
