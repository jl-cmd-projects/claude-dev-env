import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
    mergeMissingSettingsDefaults,
    settingsDefaultsFromPackageSettings,
} from './merge_settings_defaults.mjs';

const PACKAGE_SETTINGS_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'settings.json');
const REMINDER_OFF_ENV = {
    CLAUDE_CODE_TODO_REMINDER_MODE: 'off',
    CLAUDE_CODE_SILENT_TURN_REMINDER: '0',
    CLAUDE_CODE_SILENT_TURN_REMINDER_TURNS: '100000',
};

function packageSettingsDefaults() {
    return settingsDefaultsFromPackageSettings(JSON.parse(readFileSync(PACKAGE_SETTINGS_PATH, 'utf8')));
}

test('settingsDefaultsFromPackageSettings excludes managed lists', () => {
    const packageSettings = {
        permissions: { allow: ['Read'] },
        advisorModel: 'fable',
        env: { EDITOR: 'code' },
    };

    assert.deepEqual(settingsDefaultsFromPackageSettings(packageSettings), {
        advisorModel: 'fable',
        env: { EDITOR: 'code' },
    });
});

test('settingsDefaultsFromPackageSettings ignores non-object sources', () => {
    for (const packageSettings of [null, undefined, [], 'settings']) {
        assert.deepEqual(settingsDefaultsFromPackageSettings(packageSettings), {});
    }
});

test('mergeMissingSettingsDefaults adds absent keys and keeps present values', () => {
    const targetSettings = { advisorModel: null, permissions: { allow: ['Read'] } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            advisorModel: 'fable',
            theme: 'dark',
        }),
        { addedKeys: ['theme'] },
    );
    assert.deepEqual(targetSettings, {
        advisorModel: null,
        permissions: { allow: ['Read'] },
        theme: 'dark',
    });
});

test('mergeMissingSettingsDefaults should add a missing model entry and a missing field inside a present one', () => {
    const targetSettings = {
        modelSettings: {
            'claude-opus-5-5': { effortLevel: 'medium' },
            'claude-haiku-4-5': { effortLevel: 'low' },
        },
    };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            modelSettings: {
                'claude-haiku-5-5': { autoCompactWindow: 250000 },
                'claude-haiku-4-5': { autoCompactWindow: 250000 },
            },
        }),
        {
            addedKeys: [
                'modelSettings.claude-haiku-5-5',
                'modelSettings.claude-haiku-4-5.autoCompactWindow',
            ],
        },
    );
    assert.deepEqual(targetSettings.modelSettings, {
        'claude-opus-5-5': { effortLevel: 'medium' },
        'claude-haiku-4-5': { effortLevel: 'low', autoCompactWindow: 250000 },
        'claude-haiku-5-5': { autoCompactWindow: 250000 },
    });
});

test('mergeMissingSettingsDefaults should give each target its own copy of an added default', () => {
    const settingsDefaults = { modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 250000 } } };
    const firstTarget = {};
    const secondTarget = {};

    mergeMissingSettingsDefaults(firstTarget, settingsDefaults);
    firstTarget.modelSettings['claude-haiku-5-5'].autoCompactWindow = 200000;
    mergeMissingSettingsDefaults(secondTarget, settingsDefaults);

    assert.deepEqual(secondTarget.modelSettings, { 'claude-haiku-5-5': { autoCompactWindow: 250000 } });
});

test('mergeMissingSettingsDefaults should keep a per-model value the user already set', () => {
    const targetSettings = { modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 150000 } } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 250000 } },
        }),
        { addedKeys: [] },
    );
    assert.deepEqual(targetSettings.modelSettings, { 'claude-haiku-5-5': { autoCompactWindow: 150000 } });
});

test('mergeMissingSettingsDefaults should add a missing env variable to a present env block and keep the user values', () => {
    const targetSettings = {
        env: { CLAUDE_MERGE_REVIEW_COMMAND: 'review', CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '300000' },
    };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '100000', EDITOR: 'code' },
        }),
        { addedKeys: ['env.EDITOR'] },
    );
    assert.deepEqual(targetSettings, {
        env: {
            CLAUDE_MERGE_REVIEW_COMMAND: 'review',
            CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '300000',
            EDITOR: 'code',
        },
    });
});

test('mergeMissingSettingsDefaults should add the whole env block when the user settings have none', () => {
    const targetSettings = {};

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, { env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '100000' } }),
        { addedKeys: ['env'] },
    );
    assert.deepEqual(targetSettings, { env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '100000' } });
});

test('mergeMissingSettingsDefaults should keep a non-object env value as the user set it', () => {
    for (const userEnv of [null, ['CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS=300000']]) {
        const targetSettings = { env: structuredClone(userEnv) };

        assert.deepEqual(
            mergeMissingSettingsDefaults(targetSettings, { env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '100000' } }),
            { addedKeys: [] },
        );
        assert.deepEqual(targetSettings, { env: userEnv });
    }
});

test('package defaults land the three reminder-off variables in a fresh settings object', () => {
    const targetSettings = {};

    mergeMissingSettingsDefaults(targetSettings, packageSettingsDefaults());

    for (const [variableName, variableValue] of Object.entries(REMINDER_OFF_ENV)) {
        assert.equal(targetSettings.env[variableName], variableValue, variableName);
    }
});

test('package defaults keep the reminder-off variables a settings file already holds and add the missing one', () => {
    const userEnv = {
        CLAUDE_CODE_SILENT_TURN_REMINDER: 'false',
        CLAUDE_CODE_SILENT_TURN_REMINDER_TURNS: '5',
        EDITOR: 'code',
    };
    const targetSettings = { env: { ...userEnv } };

    mergeMissingSettingsDefaults(targetSettings, packageSettingsDefaults());

    assert.deepEqual(targetSettings.env, { ...packageSettingsDefaults().env, ...userEnv });
    assert.equal(targetSettings.env.CLAUDE_CODE_TODO_REMINDER_MODE, 'off');
});
