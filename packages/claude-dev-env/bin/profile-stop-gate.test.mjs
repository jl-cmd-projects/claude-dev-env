import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
    addOpenTasksGateToProfiles,
    otherProfileSettingsPaths,
    removeOpenTasksGateFromProfiles,
    splitUnreadableProfileSettings,
    unparsedSettingsMayHoldGate,
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

test('a profile that already runs its own copy of the gate script gets no second entry', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath } = makeHome(context);
    const ownGateCommand = `python3 ${join(homeDirectory, '.claude-profiles', 'isolated', 'hooks', 'blocking', 'open_tasks_stop_gate.py').replace(/\\/g, '/')}`;
    const profilePath = writeProfile(homeDirectory, 'isolated', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: ownGateCommand }] }] },
    });

    const allOutcomes = addOpenTasksGateToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(allOutcomes, []);
    assert.deepEqual(stopCommands(profilePath), [ownGateCommand]);
});

test('a settings.json that is not valid JSON is reported with its parse error, and an empty one counts as readable', (context) => {
    const { homeDirectory } = makeHome(context);
    const goodPath = writeProfile(homeDirectory, 'good', { outputStyle: 'plain' });
    const emptyPath = writeProfile(homeDirectory, 'empty');
    writeFileSync(emptyPath, '');
    const brokenPath = writeProfile(homeDirectory, 'broken');
    writeFileSync(brokenPath, '{"hooks":{},}');

    const { allReadablePaths, allUnreadable } = splitUnreadableProfileSettings([goodPath, emptyPath, brokenPath]);

    assert.deepEqual(allReadablePaths, [goodPath, emptyPath]);
    assert.equal(allUnreadable.length, 1);
    assert.equal(allUnreadable[0].settingsPath, brokenPath);
    assert.match(allUnreadable[0].reason, /JSON/);
});

test('a settings.json that does not parse may hold the gate when its text names this home\'s gate script, in either slash spelling', (context) => {
    const { homeDirectory, claudeHome, gateCommand } = makeHome(context);
    const forwardPath = writeProfile(homeDirectory, 'forward');
    writeFileSync(forwardPath, `{"hooks":{"Stop":[{"hooks":[{"command":"${gateCommand}"}]}]},}`);
    const escapedPath = writeProfile(homeDirectory, 'escaped');
    writeFileSync(escapedPath, `{"hooks":{"Stop":[{"hooks":[{"command":"${gateCommand.replace(/\//g, '\\\\')}"}]}]},}`);
    const otherHomePath = writeProfile(homeDirectory, 'other-home');
    writeFileSync(otherHomePath, '{"hooks":{"Stop":[{"hooks":[{"command":"python3 /opt/other/.claude/hooks/blocking/open_tasks_stop_gate.py"}]}]},}');
    const noGatePath = writeProfile(homeDirectory, 'no-gate');
    writeFileSync(noGatePath, '{"hooks":{},}');

    assert.equal(unparsedSettingsMayHoldGate(forwardPath, claudeHome), true);
    assert.equal(unparsedSettingsMayHoldGate(escapedPath, claudeHome), true);
    assert.equal(unparsedSettingsMayHoldGate(otherHomePath, claudeHome), false);
    assert.equal(unparsedSettingsMayHoldGate(noGatePath, claudeHome), false);
    assert.equal(unparsedSettingsMayHoldGate(join(homeDirectory, 'missing', 'settings.json'), claudeHome), true);
});
