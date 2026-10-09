/**
 * Installing into a profile root under ~/.claude-profiles retires the profile
 * session-title gate an earlier install left: its Stop hook and allow rule leave
 * settings.json, its files leave ~/.claude, and a second install leaves
 * settings.json byte for byte.
 */

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { join } from 'node:path';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import {
    RETIRED_SESSION_TITLE_GATE_COMMAND,
    RETIRED_SESSION_TITLE_GATE_FILE_NAME,
    RETIRED_SESSION_TITLE_GATE_PERMISSION,
} from './merge_profile_settings.mjs';

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

test('an install retires the profile gate, and a second install leaves settings.json byte for byte', () => {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cdev-profile-settings-'));
    try {
        writeFileSync(join(homeDirectory, '.gitconfig'), '');
        const profileRoot = join(homeDirectory, '.claude-profiles', 'work');
        mkdirSync(profileRoot, { recursive: true });
        const settingsPath = join(profileRoot, 'settings.json');
        writeFileSync(settingsPath, JSON.stringify({
            hooks: { Stop: [{ hooks: [{ type: 'command', command: RETIRED_SESSION_TITLE_GATE_COMMAND, timeout: 10 }] }] },
            permissions: { allow: [RETIRED_SESSION_TITLE_GATE_PERMISSION] },
        }, null, 4) + '\n');
        const retiredGatePath = join(homeDirectory, '.claude', RETIRED_SESSION_TITLE_GATE_FILE_NAME);
        mkdirSync(join(homeDirectory, '.claude'), { recursive: true });
        writeFileSync(retiredGatePath, 'gate\n');

        runCoreInstall(homeDirectory, profileRoot);
        const settingsBytesAfterFirstInstall = readFileSync(settingsPath);
        runCoreInstall(homeDirectory, profileRoot);

        assert.deepEqual(readFileSync(settingsPath), settingsBytesAfterFirstInstall, 'second install leaves settings.json byte for byte');
        assert.deepEqual(
            stopHookCommands(settingsPath).filter((eachCommand) => eachCommand.includes(RETIRED_SESSION_TITLE_GATE_FILE_NAME)),
            [],
        );
        const settings = JSON.parse(readFileSync(settingsPath, 'utf8'));
        assert.equal((settings.permissions?.allow ?? []).includes(RETIRED_SESSION_TITLE_GATE_PERMISSION), false);
        assert.equal(existsSync(retiredGatePath), false);
    } finally {
        rmSync(homeDirectory, { recursive: true, force: true });
    }
});
