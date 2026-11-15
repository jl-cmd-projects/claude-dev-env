import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

import { ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS } from './install-constants.mjs';
import {
    addStopGatesToProfiles,
    otherProfileSettingsPaths,
    removeStopGatesFromProfiles,
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

function makeTwoGateHome(context) {
    const home = makeHome(context);
    const closingGateCommand = `python3 ${join(home.claudeHome, 'hooks', 'blocking', 'closing_question_round_gate.py').replace(/\\/g, '/')}`;
    writeFileSync(home.mainSettingsPath, JSON.stringify({
        hooks: {
            Stop: [{
                hooks: [
                    { type: 'command', command: home.gateCommand, timeout: 10 },
                    { type: 'command', command: closingGateCommand, timeout: 10 },
                ],
            }],
        },
    }, null, 4));
    return { ...home, closingGateCommand };
}

function backupFileNames(settingsPath) {
    return readdirSync(dirname(settingsPath)).filter((eachName) => eachName.endsWith('.bak'));
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
    addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: allProfilePaths, homeDirectory });

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

    addStopGatesToProfiles(options);
    const secondOutcome = addStopGatesToProfiles(options);

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

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.equal(readFileSync(outcome.backupPath, 'utf8'), originalText);
});

test('removal takes out only the main gate entry and leaves the profile as it was', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath } = makeHome(context);
    const ownHooksPath = writeProfile(homeDirectory, 'own-hooks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 /opt/own/stop.py' }] }] },
    });
    const prefsOnlyPath = writeProfile(homeDirectory, 'prefs-only', { outputStyle: 'plain' });
    const allProfilePaths = [ownHooksPath, prefsOnlyPath];
    addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: allProfilePaths, homeDirectory });

    const allChangedPaths = removeStopGatesFromProfiles({ claudeHome, allProfileSettingsPaths: allProfilePaths });

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

    const allOutcomes = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

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

test('the profile Stop gates are the open tasks gate and then the closing question round gate', () => {
    assert.deepEqual(
        ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS.map((eachRelativePath) => eachRelativePath.join('/')),
        ['blocking/open_tasks_stop_gate.py', 'blocking/closing_question_round_gate.py'],
    );
    assert.ok(Object.isFrozen(ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS));
});

test('a profile gets both main gates, the open tasks gate first, each in its own Stop group', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const ownHooksPath = writeProfile(homeDirectory, 'own-hooks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 /opt/own/stop.py' }] }] },
    });

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [ownHooksPath], homeDirectory });

    assert.deepEqual(stopCommands(ownHooksPath), ['python3 /opt/own/stop.py', gateCommand, closingGateCommand]);
    assert.equal(outcome.additions.length, 2);
    assert.equal(JSON.parse(readFileSync(ownHooksPath, 'utf8')).hooks.Stop.length, 3);
});

test('a profile that already holds the open tasks gate gets only the closing question round gate', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const profilePath = writeProfile(homeDirectory, 'holds-open-tasks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: gateCommand, timeout: 10 }] }] },
    });

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(stopCommands(profilePath), [gateCommand, closingGateCommand]);
    assert.equal(outcome.additions.length, 1);
    assert.ok(outcome.additions[0].includes('closing_question_round_gate.py'));
});

test('a profile that already holds the closing question round gate gets only the open tasks gate', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const profilePath = writeProfile(homeDirectory, 'holds-closing-round', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: closingGateCommand, timeout: 10 }] }] },
    });

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(stopCommands(profilePath), [closingGateCommand, gateCommand]);
    assert.equal(outcome.additions.length, 1);
    assert.ok(outcome.additions[0].includes('open_tasks_stop_gate.py'));
});

test('an older spelling of the closing question round gate alone is replaced, the open tasks entry stays, and the backup holds the file as it was', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const staleClosingCommand = closingGateCommand.replace(/^python3/, '/usr/bin/python3.9');
    const profilePath = writeProfile(homeDirectory, 'stale-closing', {
        hooks: {
            Stop: [
                { hooks: [{ type: 'command', command: gateCommand, timeout: 10 }] },
                { hooks: [{ type: 'command', command: staleClosingCommand }] },
            ],
        },
    });
    const originalText = readFileSync(profilePath, 'utf8');

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(stopCommands(profilePath), [gateCommand, closingGateCommand]);
    assert.equal(outcome.additions.length, 1);
    assert.equal(readFileSync(outcome.backupPath, 'utf8'), originalText);
});

test('an older spelling of the open tasks gate alone is replaced and the closing question round entry stays', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const staleOpenTasksCommand = gateCommand.replace(/^python3/, '/usr/bin/python3.9');
    const profilePath = writeProfile(homeDirectory, 'stale-open-tasks', {
        hooks: {
            Stop: [
                { hooks: [{ type: 'command', command: staleOpenTasksCommand }] },
                { hooks: [{ type: 'command', command: closingGateCommand, timeout: 10 }] },
            ],
        },
    });

    const [outcome] = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(stopCommands(profilePath), [closingGateCommand, gateCommand]);
    assert.equal(outcome.additions.length, 1);
});

test('a second run with both gates in place adds nothing and writes no second backup', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, gateCommand, closingGateCommand } = makeTwoGateHome(context);
    const profilePath = writeProfile(homeDirectory, 'prefs-only', { outputStyle: 'plain' });
    const options = { mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory };

    addStopGatesToProfiles({ ...options, now: new Date('2030-01-01T00:00:00Z') });
    const [secondOutcome] = addStopGatesToProfiles({ ...options, now: new Date('2030-01-02T00:00:00Z') });

    assert.deepEqual(stopCommands(profilePath), [gateCommand, closingGateCommand]);
    assert.deepEqual(secondOutcome.additions, []);
    assert.equal(secondOutcome.backupPath, null);
    assert.equal(backupFileNames(profilePath).length, 1);
});

test('removal takes out both main gates and leaves the profile as it was', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath } = makeTwoGateHome(context);
    const ownHooksPath = writeProfile(homeDirectory, 'own-hooks', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 /opt/own/stop.py' }] }] },
    });
    const prefsOnlyPath = writeProfile(homeDirectory, 'prefs-only', { outputStyle: 'plain' });
    const allProfilePaths = [ownHooksPath, prefsOnlyPath];
    addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: allProfilePaths, homeDirectory });

    const allChangedPaths = removeStopGatesFromProfiles({ claudeHome, allProfileSettingsPaths: allProfilePaths });

    assert.deepEqual(allChangedPaths, allProfilePaths);
    assert.deepEqual(stopCommands(ownHooksPath), ['python3 /opt/own/stop.py']);
    assert.deepEqual(JSON.parse(readFileSync(prefsOnlyPath, 'utf8')), { outputStyle: 'plain' });
});

test('removal takes out a closing question round entry from a profile that holds no open tasks entry', (context) => {
    const { homeDirectory, claudeHome, closingGateCommand } = makeTwoGateHome(context);
    const profilePath = writeProfile(homeDirectory, 'closing-only', {
        outputStyle: 'plain',
        hooks: { Stop: [{ hooks: [{ type: 'command', command: closingGateCommand, timeout: 10 }] }] },
    });

    const allChangedPaths = removeStopGatesFromProfiles({ claudeHome, allProfileSettingsPaths: [profilePath] });

    assert.deepEqual(allChangedPaths, [profilePath]);
    assert.deepEqual(JSON.parse(readFileSync(profilePath, 'utf8')), { outputStyle: 'plain' });
});

test('a profile that runs its own copy of the open tasks gate still gets the main closing question round gate', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath, closingGateCommand } = makeTwoGateHome(context);
    const ownGateCommand = `python3 ${join(homeDirectory, '.claude-profiles', 'isolated', 'hooks', 'blocking', 'open_tasks_stop_gate.py').replace(/\\/g, '/')}`;
    const profilePath = writeProfile(homeDirectory, 'isolated', {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: ownGateCommand }] }] },
    });

    addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(stopCommands(profilePath), [ownGateCommand, closingGateCommand]);
});

test('a profile that runs its own copy of both gates gets no entry and no outcome', (context) => {
    const { homeDirectory, claudeHome, mainSettingsPath } = makeTwoGateHome(context);
    const ownHooksDirectory = join(homeDirectory, '.claude-profiles', 'isolated', 'hooks', 'blocking');
    const allOwnCommands = ['open_tasks_stop_gate.py', 'closing_question_round_gate.py']
        .map((eachScriptName) => `python3 ${join(ownHooksDirectory, eachScriptName).replace(/\\/g, '/')}`);
    const profilePath = writeProfile(homeDirectory, 'isolated', {
        hooks: { Stop: [{ hooks: allOwnCommands.map((eachCommand) => ({ type: 'command', command: eachCommand })) }] },
    });

    const allOutcomes = addStopGatesToProfiles({ mainSettingsPath, claudeHome, allProfileSettingsPaths: [profilePath], homeDirectory });

    assert.deepEqual(allOutcomes, []);
    assert.deepEqual(stopCommands(profilePath), allOwnCommands);
});

test('a settings.json that does not parse may hold a gate when its text names only the closing question round script', (context) => {
    const { homeDirectory, claudeHome, closingGateCommand } = makeTwoGateHome(context);
    const closingOnlyPath = writeProfile(homeDirectory, 'closing-only');
    writeFileSync(closingOnlyPath, `{"hooks":{"Stop":[{"hooks":[{"command":"${closingGateCommand}"}]}]},}`);
    const otherHomePath = writeProfile(homeDirectory, 'other-home');
    writeFileSync(otherHomePath, '{"hooks":{"Stop":[{"hooks":[{"command":"python3 /opt/other/.claude/hooks/blocking/closing_question_round_gate.py"}]}]},}');

    assert.equal(unparsedSettingsMayHoldGate(closingOnlyPath, claudeHome), true);
    assert.equal(unparsedSettingsMayHoldGate(otherHomePath, claudeHome), false);
});
