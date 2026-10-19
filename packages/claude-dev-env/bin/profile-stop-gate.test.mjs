import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
    addOpenTasksGateToProfiles,
    otherProfileSettingsPaths,
    removeOpenTasksGateFromProfiles,
} from './profile-stop-gate.mjs';

function makeHome(context) {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cde-profile-gate-'));
    context.after(() => rmSync(homeDirectory, { recursive: true, force: true }));
    const claudeHome = join(homeDirectory, '.claude');
    mkdirSync(claudeHome, { recursive: true });
    const gateCommand = `python3 ${join(claudeHome, 'hooks', 'blocking', 'open_tasks_stop_gate.py').replace(/\\/g, '/')}`;
    const mainSettingsPath = join(claudeHome, 'settings.json');
    writeFileSync(mainSettingsPath, JSON.stringify({
        hooks: { Stop: [{ hooks: [{ type: 'command', command: gateCommand, timeout: 10 }] }] },
    }, null, 4));
    return { homeDirectory, claudeHome, mainSettingsPath, gateCommand };
}

function writeProfile(homeDirectory, name, settings) {
    const profileDirectory = join(homeDirectory, '.claude-profiles', name);
    mkdirSync(profileDirectory, { recursive: true });
    const settingsPath = join(profileDirectory, 'settings.json');
    if (settings !== undefined) writeFileSync(settingsPath, JSON.stringify(settings, null, 4));
    return settingsPath;
}

function stopCommands(settingsPath) {
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8'));
    return (settings.hooks?.Stop ?? []).flatMap((eachGroup) => eachGroup.hooks.map((eachHook) => eachHook.command));
}

test('every profile with its own settings.json gets the main gate entry', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand } = makeHome(context);
    const ownHooksPath = writeProfile(homeDirectory, 'own-hooks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 /opt/own/stop.py' }] }] },
    });
    const prefsOnlyPath = writeProfile(homeDirectory, 'prefs-only', { outputStyle: 'plain' });
    writeProfile(homeDirectory, 'no-settings');

    const allProfilePaths = otherProfileSettingsPaths({ homeDirectory, environment: {}, mainSettingsPath });
    addOpenTasksGateToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: allProfilePaths, homeDirectory });

    assert.deepEqual(allProfilePaths.sort(), [ownHooksPath, prefsOnlyPath].sort());
    assert.deepEqual(stopCommands(ownHooksPath), ['python3 /opt/own/stop.py', gateCommand]);
    assert.deepEqual(stopCommands(prefsOnlyPath), [gateCommand]);
    assert.equal(JSON.parse(readFileSync(prefsOnlyPath, 'utf8')).outputStyle, 'plain');
});

test('a profile whose settings.json links to the main settings is left out', (context) => {
    const { homeDirectory, mainSettingsPath } = makeHome(context);
    const linkedPath = writeProfile(homeDirectory, 'linked');
    try {
        symlinkSync(mainSettingsPath, linkedPath, 'file');
    } catch (error) {
        if (error.code === 'EPERM') return context.skip('this account cannot create symlinks');
        throw error;
    }

    assert.deepEqual(otherProfileSettingsPaths({ homeDirectory, environment: {}, mainSettingsPath }), []);
});

test('a second run adds nothing, and an older interpreter spelling is replaced', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand } = makeHome(context);
    const staleCommand = gateCommand.replace(/^python3/, '/usr/bin/python3.9');
    const profilePath = writeProfile(homeDirectory, 'stale', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: staleCommand }] }] },
    });
    const options = { mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory };

    addOpenTasksGateToProfiles(options);
    const secondOutcome = addOpenTasksGateToProfiles(options);

    assert.deepEqual(stopCommands(profilePath), [gateCommand]);
    assert.deepEqual(secondOutcome[0].additions, []);
});

test('replacing an older spelling backs up the file as it was before the replacement', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand } = makeHome(context);
    const staleCommand = gateCommand.replace(/^python3/, '/usr/bin/python3.9');
    const profilePath = writeProfile(homeDirectory, 'stale', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: staleCommand }] }] },
    });
    const originalText = readFileSync(profilePath, 'utf8');

    const [outcome] = addOpenTasksGateToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.equal(readFileSync(outcome.backupPath, 'utf8'), originalText);
});

test('removal takes out only the main gate entry and leaves the profile as it was', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath } = makeHome(context);
    const ownHooksPath = writeProfile(homeDirectory, 'own-hooks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 /opt/own/stop.py' }] }] },
    });
    const prefsOnlyPath = writeProfile(homeDirectory, 'prefs-only', { outputStyle: 'plain' });
    const allProfilePaths = [ownHooksPath, prefsOnlyPath];
    addOpenTasksGateToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: allProfilePaths, homeDirectory });

    const allChangedPaths = removeOpenTasksGateFromProfiles({ claudeHome, allProfileSettingsPaths: allProfilePaths });

    assert.deepEqual(allChangedPaths, allProfilePaths);
    assert.deepEqual(stopCommands(ownHooksPath), ['python3 /opt/own/stop.py']);
    assert.deepEqual(JSON.parse(readFileSync(prefsOnlyPath, 'utf8')), { outputStyle: 'plain' });
});
