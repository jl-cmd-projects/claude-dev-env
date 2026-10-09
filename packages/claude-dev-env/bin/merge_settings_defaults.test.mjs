import { test } from 'node:test';
import { strict as assert } from 'node:assert';

import {
    mergeMissingSettingsDefaults,
    settingsDefaultsFromPackageSettings,
} from './merge_settings_defaults.mjs';

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
                'claude-haiku-5-5': { autoCompactWindow: 100000 },
                'claude-haiku-4-5': { autoCompactWindow: 100000 },
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
        'claude-haiku-4-5': { effortLevel: 'low', autoCompactWindow: 100000 },
        'claude-haiku-5-5': { autoCompactWindow: 100000 },
    });
});

test('mergeMissingSettingsDefaults should give each target its own copy of an added default', () => {
    const settingsDefaults = { modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 100000 } } };
    const firstTarget = {};
    const secondTarget = {};

    mergeMissingSettingsDefaults(firstTarget, settingsDefaults);
    firstTarget.modelSettings['claude-haiku-5-5'].autoCompactWindow = 200000;
    mergeMissingSettingsDefaults(secondTarget, settingsDefaults);

    assert.deepEqual(secondTarget.modelSettings, { 'claude-haiku-5-5': { autoCompactWindow: 100000 } });
});

test('mergeMissingSettingsDefaults should keep a per-model value the user already set', () => {
    const targetSettings = { modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 150000 } } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            modelSettings: { 'claude-haiku-5-5': { autoCompactWindow: 100000 } },
        }),
        { addedKeys: [] },
    );
    assert.deepEqual(targetSettings.modelSettings, { 'claude-haiku-5-5': { autoCompactWindow: 150000 } });
});
