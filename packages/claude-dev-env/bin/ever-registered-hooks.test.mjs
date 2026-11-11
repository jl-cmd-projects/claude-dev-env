import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { EVER_REGISTERED_HOOK_RELATIVE_PATHS } from './ever-registered-hooks.mjs';
import { managedHookScriptRelativePaths } from './install.mjs';

const SHIPPED_HOOKS_CONFIG = JSON.parse(
    readFileSync(new URL('../hooks/hooks.json', import.meta.url), 'utf8'),
);

test('EVER_REGISTERED_HOOK_RELATIVE_PATHS includes every script the package registers or prunes by name', () => {
    const allUncoveredPaths = [...managedHookScriptRelativePaths(SHIPPED_HOOKS_CONFIG)].filter(
        relativePath => !EVER_REGISTERED_HOOK_RELATIVE_PATHS.has(relativePath),
    );

    assert.deepEqual(
        allUncoveredPaths,
        [],
        'add each new registration here so a later release that drops it still removes it from settings',
    );
});

test('EVER_REGISTERED_HOOK_RELATIVE_PATHS keeps the retired merge-over-review card gate', () => {
    assert.equal(
        EVER_REGISTERED_HOOK_RELATIVE_PATHS.has('blocking/merge_over_review_offer_gate.py'),
        true,
    );
});
