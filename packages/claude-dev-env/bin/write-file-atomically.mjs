/**
 * Replace a file's contents so a kill at any point leaves a whole file.
 *
 * The new contents go to a temporary file beside the target, and a rename
 * moves that file over the target. A run that stops before the rename leaves
 * the prior file as it was; a run that stops after it leaves the new file.
 * A write that throws removes its temporary file before the error goes on.
 *
 * A target that is a symbolic link keeps the link: the write lands on the
 * file the link resolves to. A target that already exists keeps its mode.
 *
 * ::
 *
 *     writeFileAtomically(settingsPath, JSON.stringify(settings, null, 4) + '\n')
 */

import { randomBytes } from 'node:crypto';
import { chmodSync, lstatSync, readlinkSync, realpathSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';

import { renameSyncRetryingWhileBusy } from './git_hooks_installer.mjs';

const TEMPORARY_NAME_RANDOM_BYTE_COUNT = 6;
const PERMISSION_BITS_MASK = 0o7777;

/**
 * Resolve the file a write to this path lands on.
 *
 * @param {string} targetPath The path the caller names.
 * @returns {string} The path itself, or the file its link resolves to.
 */
function resolveWriteTargetPath(targetPath) {
    if (!lstatSync(targetPath, { throwIfNoEntry: false })?.isSymbolicLink()) {
        return targetPath;
    }
    try {
        return realpathSync(targetPath);
    } catch {
        return resolve(dirname(targetPath), readlinkSync(targetPath));
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
