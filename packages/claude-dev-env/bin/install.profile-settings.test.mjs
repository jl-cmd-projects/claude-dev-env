/**
 * Installing twice into a profile root under ~/.claude-profiles leaves exactly
 * one session-title gate Stop hook, and that hook runs the gate under ~/.claude.
 */

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { join } from 'node:path';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { ALL_SESSION_TITLE_GATE_RELATIVE_PATHS, SESSION_TITLE_GATE_FILE_NAME } from './merge_profile_settings.mjs';

const INSTALLER_PATH = fileURLToPath(new URL('./install.mjs', import.meta.url));

function installEnvironment(homeDirectory) {
    return {
        ...process.env,
        CLAUDE_CONFIG_DIR: undefined,
        LLM_SETTINGS_PROFILES_ROOT: undefined,
        HOME: homeDirectory,
        USERPROFILE: homeDirectory,
        GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
        CODEX_HOME: join(homeDirectory, '.codex'),
        CDE_INSTALL_PSTACK: '0',
        CDE_INSTALL_USAGE_WRAPUP: '0',
    };
}

function runCoreInstall(homeDirectory, profileRoot) {
    const installRun = spawnSync(
        process.execPath,
        [INSTALLER_PATH, '--only', 'core', '--target', profileRoot],
        { encoding: 'utf8', env: installEnvironment(homeDirectory) },
    );
    assert.equal(installRun.status, 0, installRun.stdout + installRun.stderr);
}

function stopHookCommands(settingsPath) {
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8'));
    return (settings.hooks?.Stop ?? []).flatMap(
        (eachGroup) => (eachGroup.hooks ?? []).map((eachHook) => eachHook.command.replace(/\\/g, '/')),
    );
}

test('two installs into a profile root keep one gate Stop hook that runs the gate under ~/.claude', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-profile-settings-'));
    try {
        writeFileSync(join(homeDirectory, '.gitconfig'), '');
        const profileRoot = join(homeDirectory, '.claude-profiles', 'work');
        mkdirSync(profileRoot, { recursive: true });
        const settingsPath = join(profileRoot, 'settings.json');
        const forwardSlashedHome = homeDirectory.replace(/\\/g, '/');
        const expectedGateCommand = `python3 ${forwardSlashedHome}/.claude/${SESSION_TITLE_GATE_FILE_NAME}`;

        runCoreInstall(homeDirectory, profileRoot);
        runCoreInstall(homeDirectory, profileRoot);

        const allGateCommands = stopHookCommands(settingsPath)
            .filter((eachCommand) => eachCommand.includes(SESSION_TITLE_GATE_FILE_NAME));
        assert.deepEqual(allGateCommands, [expectedGateCommand]);
        for (const eachRelativePath of ALL_SESSION_TITLE_GATE_RELATIVE_PATHS) {
            assert.ok(
                existsSync(join(homeDirectory, '.claude', eachRelativePath)),
                `${eachRelativePath} is installed under ~/.claude`,
            );
        }
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});
