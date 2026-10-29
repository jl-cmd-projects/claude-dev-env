/**
 * Publish Claude Code lookup paths that point into the agents home.
 *
 * Agents, hooks, and scripts live under the agents home. Claude Code discovers
 * them at `managedRoot/<name>`, so the installer writes those paths as
 * directory pointers (a POSIX symlink, or a Windows junction). The skills
 * lookup is a folder of pointers, one per shipped skill, so Claude reads
 * the shared skills while the agents home keeps the skill files and the plugin
 * links. One helper owns the create, refresh, and relocate steps.
 */

import {
    existsSync,
    lstatSync,
    mkdirSync,
    readlinkSync,
    readdirSync,
    renameSync,
    rmSync,
    symlinkSync,
    unlinkSync,
} from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { normalizePathForComparison } from './resolve-install-root.mjs';

export const DIRECTORY_POINTER_TYPE_JUNCTION = 'junction';
export const DIRECTORY_POINTER_TYPE_DIR = 'dir';
export const POINTER_ACTION_ALREADY_POINTING = 'already-pointing';
export const POINTER_ACTION_CREATED = 'created';

/**
 * Directory-pointer type this host uses.
 *
 * Windows receives a junction so the pointer works without Developer Mode.
 * POSIX receives a directory symlink.
 *
 * @param {string} [platform]
 * @returns {typeof DIRECTORY_POINTER_TYPE_JUNCTION | typeof DIRECTORY_POINTER_TYPE_DIR}
 */
export function directoryPointerTypeForPlatform(platform = process.platform) {
    return platform === 'win32'
        ? DIRECTORY_POINTER_TYPE_JUNCTION
        : DIRECTORY_POINTER_TYPE_DIR;
}

/**
 * Report whether pointerPath is a directory pointer whose target is targetPath.
 *
 * @param {string} pointerPath
 * @param {string} targetPath
 * @returns {boolean}
 */
export function isDirectoryPointerTo(pointerPath, targetPath) {
    const pathKind = readPathKind(pointerPath);
    if (pathKind !== 'symlink') {
        return false;
    }
    const linkTarget = readlinkSync(pointerPath);
    const resolvedLinkTarget = resolve(dirname(pointerPath), linkTarget);
    return normalizePathForComparison(resolvedLinkTarget)
        === normalizePathForComparison(resolve(targetPath));
}

/**
 * Report whether linkPath is a symbolic link that does not aim at targetPath.
 *
 * @param {string} linkPath
 * @param {string} targetPath
 * @returns {boolean}
 */
export function isLinkToOtherDirectory(linkPath, targetPath) {
    return readPathKind(linkPath) === 'symlink' && !isDirectoryPointerTo(linkPath, targetPath);
}

/**
 * Make pointerPath a directory pointer to targetPath.
 *
 * A real directory already sitting at the lookup path is merged into the
 * target, then the pointer is written. A pointer that already aims at the
 * target is left in place.
 *
 * @param {string} pointerPath Claude Code lookup path (for example `~/.claude/skills`).
 * @param {string} targetPath Canonical directory (for example `~/.agents/skills`).
 * @param {{ pointerType?: string }} [options]
 * @returns {{ action: string, pointerPath: string, targetPath: string }}
 */
export function ensureDirectoryPointer(pointerPath, targetPath, options = {}) {
    const pointerType = options.pointerType ?? directoryPointerTypeForPlatform();
    const resolvedTarget = resolve(targetPath);
    const resolvedPointer = resolve(pointerPath);
    mkdirSync(resolvedTarget, { recursive: true });

    if (isDirectoryPointerTo(resolvedPointer, resolvedTarget)) {
        return {
            action: POINTER_ACTION_ALREADY_POINTING,
            pointerPath: resolvedPointer,
            targetPath: resolvedTarget,
        };
    }

    const pathKind = readPathKind(resolvedPointer);
    if (pathKind === 'symlink') {
        unlinkSync(resolvedPointer);
    } else if (pathKind === 'directory') {
        mergeDirectoryContents(resolvedPointer, resolvedTarget);
        rmSync(resolvedPointer, { recursive: true, force: true });
    } else if (pathKind === 'file') {
        throw new Error(
            `Cannot publish a directory pointer: ${resolvedPointer} is a file`,
        );
    }

    mkdirSync(dirname(resolvedPointer), { recursive: true });
    symlinkSync(resolvedTarget, resolvedPointer, pointerType);
    return {
        action: POINTER_ACTION_CREATED,
        pointerPath: resolvedPointer,
        targetPath: resolvedTarget,
    };
}

/**
 * Make lookupDirectory a folder with one directory pointer per directory in
 * installDirectory.
 *
 * A pointer left by an earlier install is replaced by the folder. A link that
 * aims at any other directory is refused, so the folder never writes into a
 * directory the installer does not own. A per-skill link that aims at another
 * directory is left in place. A link whose target under
 * installDirectory is gone is removed. A symbolic link inside installDirectory
 * is not linked here, which keeps plugin links out of this folder. A
 * directory in lookupDirectory that installDirectory lacks is a personal skill
 * and stays where it is. A file in a same-named lookup directory that
 * installDirectory already holds moves to conflictBackupDirectory before the
 * merge, so a local edit survives.
 *
 * @param {string} lookupDirectory Claude lookup path (for example `~/.claude/skills`).
 * @param {string} installDirectory Canonical skills folder (for example `~/.agents/skills`).
 * @param {string} conflictBackupDirectory Folder that receives displaced lookup files.
 * @returns {{ createdLinkPaths: string[], linkPaths: string[] }} The links this
 *   call created, and every link that points at a shipped skill after the call.
 */
export function ensureLinkedSkillFolder(lookupDirectory, installDirectory, conflictBackupDirectory) {
    const resolvedLookup = resolve(lookupDirectory);
    const resolvedInstall = resolve(installDirectory);
    mkdirSync(resolvedInstall, { recursive: true });

    const lookupKind = readPathKind(resolvedLookup);
    if (lookupKind === 'symlink') {
        if (!isDirectoryPointerTo(resolvedLookup, resolvedInstall)) {
            throw new Error(
                `Cannot publish linked skills: ${resolvedLookup} is a link to another directory`,
            );
        }
        unlinkSync(resolvedLookup);
    } else if (lookupKind === 'file') {
        throw new Error(`Cannot publish linked skills: ${resolvedLookup} is a file`);
    }
    mkdirSync(resolvedLookup, { recursive: true });

    removeDanglingLinksInto(resolvedLookup, resolvedInstall);
    const createdLinkPaths = [];
    const linkPaths = [];
    for (const eachEntry of readdirSync(resolvedInstall, { withFileTypes: true })) {
        if (!eachEntry.isDirectory()) continue;
        const linkPath = join(resolvedLookup, eachEntry.name);
        const targetPath = join(resolvedInstall, eachEntry.name);
        if (isLinkToOtherDirectory(linkPath, targetPath)) continue;
        if (readPathKind(linkPath) === 'directory') {
            setAsideConflictingEntries(linkPath, targetPath, join(conflictBackupDirectory, eachEntry.name));
        }
        const publication = ensureDirectoryPointer(linkPath, targetPath);
        linkPaths.push(linkPath);
        if (publication.action === POINTER_ACTION_CREATED) {
            createdLinkPaths.push(linkPath);
        }
    }
    return { createdLinkPaths, linkPaths };
}

/**
 * Remove a directory pointer when it aims at the expected target.
 *
 * @param {string} pointerPath
 * @param {string} targetPath
 * @returns {boolean} True when this call unlinked the pointer.
 */
export function unlinkDirectoryPointerIfMatch(pointerPath, targetPath) {
    if (!isDirectoryPointerTo(pointerPath, targetPath)) {
        return false;
    }
    unlinkSync(pointerPath);
    return true;
}

/**
 * @param {string} absolutePath
 * @returns {'missing' | 'symlink' | 'directory' | 'file' | 'other'}
 */
export function readPathKind(absolutePath) {
    let stats;
    try {
        stats = lstatSync(absolutePath);
    } catch (readError) {
        if (readError && readError.code === 'ENOENT') {
            return 'missing';
        }
        throw readError;
    }
    if (stats.isSymbolicLink()) {
        return 'symlink';
    }
    if (stats.isDirectory()) {
        return 'directory';
    }
    if (stats.isFile()) {
        return 'file';
    }
    return 'other';
}

/**
 * Remove links in lookupDirectory whose target sits under installDirectory and
 * no longer exists.
 *
 * @param {string} lookupDirectory
 * @param {string} installDirectory
 * @returns {void}
 */
function removeDanglingLinksInto(lookupDirectory, installDirectory) {
    for (const eachEntry of readdirSync(lookupDirectory, { withFileTypes: true })) {
        if (!eachEntry.isSymbolicLink()) continue;
        const linkPath = join(lookupDirectory, eachEntry.name);
        const linkTarget = resolve(lookupDirectory, readlinkSync(linkPath));
        const targetOffset = relative(installDirectory, linkTarget);
        const targetIsInside = targetOffset !== ''
            && !isAbsolute(targetOffset)
            && targetOffset.split(sep)[0] !== '..';
        if (targetIsInside && !existsSync(linkPath)) {
            unlinkSync(linkPath);
        }
    }
}

/**
 * Move each entry in sourceDirectory that destinationDirectory already holds
 * into backupDirectory, keeping its relative path. A directory that exists on
 * both sides is walked the same way. Entries the destination lacks stay in
 * place for the merge that follows.
 *
 * @param {string} sourceDirectory
 * @param {string} destinationDirectory
 * @param {string} backupDirectory
 * @returns {void}
 */
function setAsideConflictingEntries(sourceDirectory, destinationDirectory, backupDirectory) {
    for (const eachEntry of readdirSync(sourceDirectory, { withFileTypes: true })) {
        const sourceChild = join(sourceDirectory, eachEntry.name);
        const destinationChild = join(destinationDirectory, eachEntry.name);
        if (!existsSync(destinationChild)) continue;
        if (eachEntry.isDirectory() && readPathKind(destinationChild) === 'directory') {
            setAsideConflictingEntries(sourceChild, destinationChild, join(backupDirectory, eachEntry.name));
            continue;
        }
        mkdirSync(backupDirectory, { recursive: true });
        renameSync(sourceChild, join(backupDirectory, eachEntry.name));
        console.log(`  Kept the local copy of ${sourceChild} in ${backupDirectory}`);
    }
}

/**
 * Move unique entries from sourceDirectory into destinationDirectory.
 *
 * An entry that already exists at the destination stays there. Nested
 * directories merge the same way. Leftover source entries are removed by the
 * caller with the source directory.
 *
 * @param {string} sourceDirectory
 * @param {string} destinationDirectory
 * @returns {void}
 */
function mergeDirectoryContents(sourceDirectory, destinationDirectory) {
    mkdirSync(destinationDirectory, { recursive: true });
    const allEntries = readdirSync(sourceDirectory, { withFileTypes: true });
    for (const eachEntry of allEntries) {
        const sourceChild = join(sourceDirectory, eachEntry.name);
        const destinationChild = join(destinationDirectory, eachEntry.name);
        if (!existsSync(destinationChild)) {
            renameSync(sourceChild, destinationChild);
            continue;
        }
        if (eachEntry.isDirectory() && readPathKind(destinationChild) === 'directory') {
            mergeDirectoryContents(sourceChild, destinationChild);
        }
    }
}
