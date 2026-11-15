/**
 * Replace a file's contents so a kill at any point leaves a whole file.
 *
 * The new contents go to a temporary file beside the target, and a rename
 * moves that file over the target. A run that stops before the rename leaves
 * the prior file as it was; a run that stops after it leaves the new file.
 * A write that throws removes its temporary file before the error goes on.
 * Each write first removes this target's stale temporary files, the ones a
 * killed writer left behind.
 *
 * A target that is a symbolic link keeps the link: the write lands on the
 * file the link resolves to. A target that already exists keeps its mode.
 *
 * ::
 *
 *     writeFileAtomically(settingsPath, JSON.stringify(settings, null, 4) + '\n')
 */

import { randomBytes } from 'node:crypto';
import { chmodSync, lstatSync, readdirSync, readlinkSync, realpathSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';

import { renameSyncRetryingWhileBusy } from './git_hooks_installer.mjs';

const TEMPORARY_NAME_RANDOM_BYTE_COUNT = 6;
const PERMISSION_BITS_MASK = 0o7777;
const STALE_TEMPORARY_FILE_AGE_MS = 10 * 60 * 1000;
const REGULAR_EXPRESSION_SPECIAL_CHARACTERS = /[.*+?^${}()|[\]\\]/g;
const MAXIMUM_LINK_COUNT = 40;


/**
 * Say whether a process with this id runs on this machine now.
 *
 * @param {number} processId The process id a temporary file name carries.
 * @returns {boolean} True when the process exists, or exists and belongs to another user.
 */
function processIsRunning(processId) {
    try {
        process.kill(processId, 0);
        return true;
    } catch (probeError) {
        return probeError.code === 'EPERM';
    }
}


/**
 * Remove temporary files that a killed write of this target left behind.
 *
 * A temporary file is stale when its name carries a process id that no
 * longer runs and it is older than ten minutes::
 *
 *     .settings.json.4242.a1b2c3d4e5f6.tmp   process 4242 gone, an hour old -> removed
 *     .settings.json.4242.a1b2c3d4e5f6.tmp   process 4242 gone, a minute old -> kept
 *     .settings.json.5151.a1b2c3d4e5f6.tmp   process 5151 runs              -> kept
 *
 * A file that cannot be read or removed stays.
 *
 * @param {string} writeTargetPath The file the write lands on.
 * @returns {void}
 */
function removeStaleTemporaryFiles(writeTargetPath) {
    const targetDirectory = dirname(writeTargetPath);
    const escapedName = basename(writeTargetPath).replace(REGULAR_EXPRESSION_SPECIAL_CHARACTERS, '\\$&');
    const temporaryNamePattern = new RegExp(`^\\.${escapedName}\\.(\\d+)\\.[0-9a-f]+\\.tmp$`);
    let allEntryNames;
    try {
        allEntryNames = readdirSync(targetDirectory);
    } catch {
        return;
    }
    for (const eachName of allEntryNames) {
        const nameMatch = temporaryNamePattern.exec(eachName);
        if (!nameMatch) {
            continue;
        }
        const writerProcessId = Number(nameMatch[1]);
        if (writerProcessId === process.pid || processIsRunning(writerProcessId)) {
            continue;
        }
        const temporaryPath = join(targetDirectory, eachName);
        try {
            if (Date.now() - statSync(temporaryPath).mtimeMs > STALE_TEMPORARY_FILE_AGE_MS) {
                rmSync(temporaryPath, { force: true });
            }
        } catch {
            continue;
        }
    }
}

/**
 * Resolve the file a write to this path lands on.
 *
 * A chain of links is followed to its last entry, which may not exist yet::
 *
 *     profile/settings.json -> dotfiles/settings.json -> store/settings.json (missing)
 *     -> store/settings.json
 *
 * @param {string} targetPath The path the caller names.
 * @returns {string} The path itself, or the file its chain of links ends at.
 * @throws {Error} With code ELOOP when the chain is longer than the link limit.
 */
function resolveWriteTargetPath(targetPath) {
    if (!lstatSync(targetPath, { throwIfNoEntry: false })?.isSymbolicLink()) {
        return targetPath;
    }
    try {
        return realpathSync(targetPath);
    } catch {
        let currentPath = targetPath;
        for (let linkCount = 0; linkCount < MAXIMUM_LINK_COUNT; linkCount += 1) {
            if (!lstatSync(currentPath, { throwIfNoEntry: false })?.isSymbolicLink()) {
                return currentPath;
            }
            currentPath = resolve(dirname(currentPath), readlinkSync(currentPath));
        }
        throw Object.assign(new Error(`ELOOP: too many links to resolve '${targetPath}'`), { code: 'ELOOP' });
    }
}

/**
 * Write contents to a path through a temporary file and a rename.
 *
 * @param {string} targetPath The file to create or replace.
 * @param {string | Uint8Array} contents The complete new contents.
 * @returns {void}
 */
export function writeFileAtomically(targetPath, contents) {
    const writeTargetPath = resolveWriteTargetPath(targetPath);
    removeStaleTemporaryFiles(writeTargetPath);
    const priorStats = statSync(writeTargetPath, { throwIfNoEntry: false });
    const temporaryPath = join(
        dirname(writeTargetPath),
        `.${basename(writeTargetPath)}.${process.pid}.${randomBytes(TEMPORARY_NAME_RANDOM_BYTE_COUNT).toString('hex')}.tmp`,
    );
    try {
        writeFileSync(temporaryPath, contents, { flag: 'wx' });
        if (priorStats) {
            chmodSync(temporaryPath, priorStats.mode & PERMISSION_BITS_MASK);
        }
        renameSyncRetryingWhileBusy(temporaryPath, writeTargetPath);
    } catch (writeError) {
        rmSync(temporaryPath, { force: true });
        throw writeError;
    }
}
