import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import {
    ALL_SESSION_TITLE_GATE_RELATIVE_PATHS,
    AUTO_MODE_DEFAULTS_ENTRY,
    DECLARED_PROFILE_SETTINGS,
    SESSION_TITLE_GATE_FILE_NAME,
    SESSION_TITLE_GATE_SOURCE_DIRECTORY,
    discoverProfileSettingsPaths,
    mergeProfileSettings,
} from './merge_profile_settings.mjs';

const FIXED_NOW = new Date('2026-10-04T12:00:00.000Z');
const BACKUP_SUFFIX = '.2026-10-04T12-00-00-000Z.bak';
const PERMISSION_ALLOW_ITEMS = DECLARED_PROFILE_SETTINGS
    .find((eachEntry) => eachEntry.keyPath.join('.') === 'permissions.allow').items;
const AUTO_MODE_ALLOW_ITEMS = DECLARED_PROFILE_SETTINGS
    .find((eachEntry) => eachEntry.keyPath.join('.') === 'autoMode.allow').items;

function makeHome() {
    return mkdtempSync(join(tmpdir(), 'cde-profile-settings-'));
}

function writeSettings(settingsPath, settings) {
    mkdirSync(join(settingsPath, '..'), { recursive: true });
    writeFileSync(settingsPath, JSON.stringify(settings, null, 4) + '\n');
}

function readSettings(settingsPath) {
    return JSON.parse(readFileSync(settingsPath, 'utf8'));
}

function backupFiles(directory) {
    return readdirSync(directory).filter((eachName) => eachName.endsWith('.bak'));
}

function expandedGateCommand(homeDirectory) {
    return `python3 ${homeDirectory.replace(/\\/g, '/')}/.claude/${SESSION_TITLE_GATE_FILE_NAME}`;
}

function stopCommands(settings) {
    return settings.hooks.Stop.flatMap((eachGroup) => eachGroup.hooks.map((eachHook) => eachHook.command));
}

test('a missing settings.json is created with every declared entry and the gate is copied', () => {
    const homeDirectory = makeHome();
    const claudeDirectory = join(homeDirectory, '.claude');
    mkdirSync(claudeDirectory);
    const settingsPath = join(claudeDirectory, 'settings.json');

    const outcome = mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.deepEqual(readSettings(settingsPath), {
        hooks: {
            Stop: [{ hooks: [{ type: 'command', command: expandedGateCommand(homeDirectory), timeout: 10 }] }],
        },
        permissions: { allow: PERMISSION_ALLOW_ITEMS },
        autoMode: { allow: AUTO_MODE_ALLOW_ITEMS },
    });
    assert.equal(outcome.files[0].backupPath, null);
    assert.deepEqual(backupFiles(claudeDirectory), []);
    for (const eachRelativePath of ALL_SESSION_TITLE_GATE_RELATIVE_PATHS) {
        assert.equal(
            readFileSync(join(claudeDirectory, eachRelativePath), 'utf8'),
            readFileSync(join(SESSION_TITLE_GATE_SOURCE_DIRECTORY, eachRelativePath), 'utf8'),
        );
    }
});

test('a gate whose constants module is missing is reported changed and the module is copied', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });
    const constantsPath = join(homeDirectory, '.claude', 'config', 'session_title_gate_constants.py');
    unlinkSync(constantsPath);

    const outcome = mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.equal(outcome.gate.changed, true);
    assert.equal(existsSync(constantsPath), true);
});

test('a file that already holds every entry is left byte for byte, with no backup', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });
    const textAfterFirstRun = readFileSync(settingsPath, 'utf8');

    const outcome = mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.deepEqual(outcome.files[0].additions, []);
    assert.equal(outcome.gate.changed, false);
    assert.equal(readFileSync(settingsPath, 'utf8'), textAfterFirstRun);
    assert.deepEqual(backupFiles(join(homeDirectory, '.claude')), []);
});

test('a partial file gains only the missing entries, keeps other keys, and is backed up first', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    const originalSettings = {
        model: 'opus',
        hooks: {
            Stop: [{ hooks: [{ type: 'command', command: expandedGateCommand(homeDirectory), timeout: 30 }] }],
            PreToolUse: [{ matcher: 'Bash', hooks: [{ type: 'command', command: 'python3 guard.py' }] }],
        },
        permissions: { allow: ['Read', 'mcp__claude-code-remote__set_session_title'], deny: ['Bash(rm:*)'] },
        autoMode: { allow: ['Pushing to my fork is allowed'], environment: ['Source control: example'] },
    };
    writeSettings(settingsPath, originalSettings);
    const originalText = readFileSync(settingsPath, 'utf8');

    const outcome = mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    const mergedSettings = readSettings(settingsPath);
    assert.equal(mergedSettings.model, 'opus');
    assert.deepEqual(mergedSettings.hooks.Stop, originalSettings.hooks.Stop);
    assert.deepEqual(mergedSettings.hooks.PreToolUse, originalSettings.hooks.PreToolUse);
    assert.deepEqual(mergedSettings.permissions.deny, ['Bash(rm:*)']);
    assert.deepEqual(mergedSettings.permissions.allow, [
        'Read',
        'mcp__claude-code-remote__set_session_title',
        ...PERMISSION_ALLOW_ITEMS.filter((eachItem) => eachItem !== 'mcp__claude-code-remote__set_session_title'),
    ]);
    assert.deepEqual(mergedSettings.autoMode.allow, ['Pushing to my fork is allowed', ...AUTO_MODE_ALLOW_ITEMS]);
    assert.ok(mergedSettings.autoMode.allow.includes(AUTO_MODE_DEFAULTS_ENTRY));
    assert.deepEqual(mergedSettings.autoMode.environment, ['Source control: example']);
    assert.equal(outcome.files[0].backupPath, `${settingsPath}${BACKUP_SUFFIX}`);
    assert.equal(readFileSync(outcome.files[0].backupPath, 'utf8'), originalText);
});

test('a gate hook written with backslashes counts as present', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    const backslashedGateCommand = `python3 ${homeDirectory.replace(/\//g, '\\')}\\.claude\\${SESSION_TITLE_GATE_FILE_NAME}`;
    writeSettings(settingsPath, {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: backslashedGateCommand, timeout: 10 }] }] },
    });

    mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.deepEqual(stopCommands(readSettings(settingsPath)), [backslashedGateCommand]);
});

test('the gate hook is added beside a different Stop hook', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    writeSettings(settingsPath, {
        hooks: { Stop: [{ hooks: [{ type: 'command', command: 'python3 other_stop.py' }] }] },
    });

    mergeProfileSettings([settingsPath], { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.deepEqual(stopCommands(readSettings(settingsPath)), ['python3 other_stop.py', expandedGateCommand(homeDirectory)]);
});

test('discovery finds the main, CLAUDE_CONFIG_DIR, and every profile settings.json once, and each is merged', () => {
    const homeDirectory = makeHome();
    const profilesRoot = join(homeDirectory, '.claude-profiles');
    mkdirSync(join(homeDirectory, '.claude'));
    writeSettings(join(profilesRoot, 'work', 'settings.json'), { model: 'work' });
    writeSettings(join(profilesRoot, 'home', 'settings.json'), { model: 'home' });
    mkdirSync(join(profilesRoot, 'work.agents'));
    const configDirectory = join(homeDirectory, 'custom-config');
    mkdirSync(configDirectory);

    const allSettingsPaths = discoverProfileSettingsPaths({
        homeDirectory,
        environment: { CLAUDE_CONFIG_DIR: configDirectory },
    });
    const allSettingsPathsWithSharedConfig = discoverProfileSettingsPaths({
        homeDirectory,
        environment: { CLAUDE_CONFIG_DIR: join(profilesRoot, 'work') },
    });
    mergeProfileSettings(allSettingsPaths, { dryRun: false, homeDirectory, now: FIXED_NOW });

    assert.deepEqual([...allSettingsPaths].sort(), [
        resolve(homeDirectory, '.claude', 'settings.json'),
        resolve(profilesRoot, 'home', 'settings.json'),
        resolve(profilesRoot, 'work', 'settings.json'),
        resolve(configDirectory, 'settings.json'),
    ].sort());
    assert.equal(allSettingsPathsWithSharedConfig.length, 3);
    for (const eachPath of allSettingsPaths) {
        assert.deepEqual(stopCommands(readSettings(eachPath)), [expandedGateCommand(homeDirectory)]);
        assert.deepEqual(readSettings(eachPath).autoMode.allow, AUTO_MODE_ALLOW_ITEMS);
    }
    assert.equal(readSettings(join(profilesRoot, 'work', 'settings.json')).model, 'work');
    assert.equal(backupFiles(join(profilesRoot, 'home')).length, 1);
});

test('a dry run reports additions and writes nothing', () => {
    const homeDirectory = makeHome();
    const settingsPath = join(homeDirectory, '.claude', 'settings.json');
    writeSettings(settingsPath, { model: 'opus' });
    const originalText = readFileSync(settingsPath, 'utf8');

    const outcome = mergeProfileSettings([settingsPath], { dryRun: true, homeDirectory, now: FIXED_NOW });

    assert.equal(outcome.files[0].additions.length, 7);
    assert.equal(outcome.gate.changed, true);
    assert.equal(readFileSync(settingsPath, 'utf8'), originalText);
    assert.deepEqual(backupFiles(join(homeDirectory, '.claude')), []);
    assert.equal(existsSync(join(homeDirectory, '.claude', SESSION_TITLE_GATE_FILE_NAME)), false);
});
