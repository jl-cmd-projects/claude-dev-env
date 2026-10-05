/**
 * An `--update` reinstall keeps every registered hook script on disk for the
 * whole run, so a live session's hook call never finds its script missing.
 */

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { INSTALL_FAULT_ENV } from './install-transaction.mjs';

const THIS_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const INSTALLER_PATH = join(THIS_DIRECTORY, 'install.mjs');
const REGISTERED_HOOK_RELATIVE_PATHS = [
    join('blocking', 'bash_post_call_dispatcher.py'),
    join('blocking', 'verify_before_acting.py'),
];

function installerEnvironment(homeDirectory) {
    const childEnvironment = {
        ...process.env,
        CLAUDE_CONFIG_DIR: undefined,
        LLM_SETTINGS_PROFILES_ROOT: undefined,
        CDE_INSTALL_PSTACK: '0',
        CDE_INSTALL_USAGE_WRAPUP: '0',
        CDE_INSTALL_SUBAGENT_MODELS: '0',
        HOME: homeDirectory,
        USERPROFILE: homeDirectory,
        GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
        CODEX_HOME: join(homeDirectory, '.codex'),
    };
    delete childEnvironment[INSTALL_FAULT_ENV];
    return childEnvironment;
}

function runUpdateWhileWatching(homeDirectory, watchedPaths) {
    return new Promise((resolvePromise, rejectPromise) => {
        const missingCountByPath = new Map();
        let outputText = '';
        let hasExited = false;
        const child = spawn(process.execPath, [INSTALLER_PATH, '--update'], {
            cwd: THIS_DIRECTORY,
            env: installerEnvironment(homeDirectory),
        });
        child.stdout.on('data', (chunk) => { outputText += chunk; });
        child.stderr.on('data', (chunk) => { outputText += chunk; });
        child.on('error', rejectPromise);
        child.on('exit', (exitCode) => {
            hasExited = true;
            resolvePromise({ exitCode, outputText, missingCountByPath });
        });
        const pollOnce = () => {
            if (hasExited) return;
            for (const watchedPath of watchedPaths) {
                if (!existsSync(watchedPath)) {
                    missingCountByPath.set(watchedPath, (missingCountByPath.get(watchedPath) ?? 0) + 1);
                }
            }
            setImmediate(pollOnce);
        };
        setImmediate(pollOnce);
    });
}

test('--update never leaves a registered hook script missing mid-install', async () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-update-hooks-'));
    try {
        const firstInstall = spawnSync(process.execPath, [INSTALLER_PATH], {
            cwd: THIS_DIRECTORY,
            encoding: 'utf8',
            env: installerEnvironment(homeDirectory),
        });
        assert.equal(firstInstall.status, 0, firstInstall.stdout + firstInstall.stderr);
        const hooksDirectory = join(homeDirectory, '.agents', 'hooks');
        const watchedPaths = REGISTERED_HOOK_RELATIVE_PATHS.map(
            (relativePath) => join(hooksDirectory, relativePath),
        );
        for (const watchedPath of watchedPaths) {
            assert.equal(existsSync(watchedPath), true, `first install wrote ${watchedPath}`);
        }

        const updateRun = await runUpdateWhileWatching(homeDirectory, watchedPaths);

        assert.equal(updateRun.exitCode, 0, updateRun.outputText);
        assert.deepEqual(
            Object.fromEntries(updateRun.missingCountByPath),
            {},
            'a registered hook script was absent while --update ran',
        );
        for (const watchedPath of watchedPaths) {
            assert.equal(existsSync(watchedPath), true, `--update left ${watchedPath} in place`);
        }
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});
