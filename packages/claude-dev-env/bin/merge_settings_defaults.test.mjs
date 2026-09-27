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
