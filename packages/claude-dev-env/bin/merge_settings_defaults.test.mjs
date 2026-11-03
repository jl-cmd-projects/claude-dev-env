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

test('mergeMissingSettingsDefaults should append the missing autoMode allow rules after the user rules and keep the rest', () => {
    const targetSettings = {
        autoMode: {
            allow: ['$defaults', 'Sample user rule'],
            environment: ['Sample environment entry'],
        },
    };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            autoMode: { allow: ['$defaults', 'Sample packaged rule one', 'Sample packaged rule two'] },
        }),
        { addedKeys: ['autoMode.allow'] },
    );
    assert.deepEqual(targetSettings, {
        autoMode: {
            allow: [
                '$defaults',
                'Sample user rule',
                'Sample packaged rule one',
                'Sample packaged rule two',
            ],
            environment: ['Sample environment entry'],
        },
    });
});

test('mergeMissingSettingsDefaults should add the packaged allow rules to an autoMode block that has no allow list', () => {
    const targetSettings = { autoMode: { environment: ['Sample environment entry'] } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, { autoMode: { allow: ['Sample packaged rule one'] } }),
        { addedKeys: ['autoMode.allow'] },
    );
    assert.deepEqual(targetSettings, {
        autoMode: {
            environment: ['Sample environment entry'],
            allow: ['Sample packaged rule one'],
        },
    });
});

test('mergeMissingSettingsDefaults should add a packaged autoMode rule that repeats in the defaults once', () => {
    const targetSettings = { autoMode: { allow: ['$defaults'] } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            autoMode: { allow: ['Sample packaged rule one', 'Sample packaged rule one'] },
        }),
        { addedKeys: ['autoMode.allow'] },
    );
    assert.deepEqual(targetSettings.autoMode.allow, ['$defaults', 'Sample packaged rule one']);
});

test('mergeMissingSettingsDefaults should keep an array env or modelSettings value as the user set it', () => {
    const targetSettings = {
        env: { SAMPLE_LIST: ['sample user value'] },
        modelSettings: { 'claude-haiku-5-5': { SAMPLE_LIST: ['sample user value'] } },
    };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, {
            env: { SAMPLE_LIST: ['sample packaged value'] },
            modelSettings: { 'claude-haiku-5-5': { SAMPLE_LIST: ['sample packaged value'] } },
        }),
        { addedKeys: [] },
    );
    assert.deepEqual(targetSettings.env.SAMPLE_LIST, ['sample user value']);
    assert.deepEqual(targetSettings.modelSettings['claude-haiku-5-5'].SAMPLE_LIST, ['sample user value']);
});

test('mergeMissingSettingsDefaults should add no autoMode rule a second time', () => {
    const settingsDefaults = { autoMode: { allow: ['Sample packaged rule one'] } };
    const targetSettings = {};

    mergeMissingSettingsDefaults(targetSettings, settingsDefaults);

    assert.deepEqual(mergeMissingSettingsDefaults(targetSettings, settingsDefaults), { addedKeys: [] });
    assert.deepEqual(targetSettings.autoMode.allow, ['Sample packaged rule one']);
});

test('mergeMissingSettingsDefaults should keep a non-list autoMode allow value as the user set it', () => {
    const targetSettings = { autoMode: { allow: 'Sample user value' } };

    assert.deepEqual(
        mergeMissingSettingsDefaults(targetSettings, { autoMode: { allow: ['Sample packaged rule one'] } }),
        { addedKeys: [] },
    );
    assert.deepEqual(targetSettings, { autoMode: { allow: 'Sample user value' } });
});
