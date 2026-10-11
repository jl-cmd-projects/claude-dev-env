import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';

import { isManagedPromptHook, mergeHooksIntoSettings, pruneManagedHooksFromSettings } from './install.mjs';

const SHIPPED_HOOKS_CONFIG = JSON.parse(readFileSync(new URL('../hooks/hooks.json', import.meta.url), 'utf8'));

const REPLY_MATCHER = 'mcp__hearthbot__reply';
const MANAGED_STATUS = 'claude-dev-env: checking each claim for its source';
const USER_PROMPT_HOOK = { type: 'prompt', prompt: 'User check. $ARGUMENTS', statusMessage: 'my own check' };

function hooksConfigWithPrompt(promptText) {
    return {
        hooks: {
            PreToolUse: [
                {
                    matcher: REPLY_MATCHER,
                    hooks: [{ type: 'prompt', prompt: promptText, timeout: 30, statusMessage: MANAGED_STATUS }],
                },
            ],
        },
    };
}

function replyHooks(settings) {
    return (settings.hooks?.PreToolUse ?? [])
        .filter(eachGroup => eachGroup.matcher === REPLY_MATCHER)
        .flatMap(eachGroup => eachGroup.hooks);
}

test('should keep one managed prompt hook across reinstalls and carry the new prompt text', () => {
    const settings = { hooks: { PreToolUse: [{ matcher: REPLY_MATCHER, hooks: [USER_PROMPT_HOOK] }] } };

    mergeHooksIntoSettings(settings, hooksConfigWithPrompt('First judge. $ARGUMENTS'), '/home/example/.claude', 'python3');
    mergeHooksIntoSettings(settings, hooksConfigWithPrompt('Second judge. $ARGUMENTS'), '/home/example/.claude', 'python3');

    assert.deepEqual(
        replyHooks(settings).map(eachHook => eachHook.prompt),
        ['User check. $ARGUMENTS', 'Second judge. $ARGUMENTS'],
    );
});

test('should remove the managed prompt hook on uninstall and keep the user prompt hook', () => {
    const settings = { hooks: { PreToolUse: [{ matcher: REPLY_MATCHER, hooks: [USER_PROMPT_HOOK] }] } };
    mergeHooksIntoSettings(settings, hooksConfigWithPrompt('Judge. $ARGUMENTS'), '/home/example/.claude', 'python3');

    pruneManagedHooksFromSettings(settings, new Set());

    assert.deepEqual(replyHooks(settings), [USER_PROMPT_HOOK]);
});

function promptHookEntries(hooksConfig) {
    return Object.entries(hooksConfig.hooks).flatMap(([eventName, matcherGroups]) => matcherGroups.flatMap(
        eachGroup => (eachGroup.hooks ?? [])
            .filter(eachHook => eachHook.type === 'prompt')
            .map(eachHook => ({ eventName, matcher: eachGroup.matcher, hook: eachHook })),
    ));
}

test('should own every prompt hook the shipped hooks.json registers, including the claim judge on reply', () => {
    const shippedEntries = promptHookEntries(SHIPPED_HOOKS_CONFIG);

    assert.ok(shippedEntries.some(
        eachEntry => eachEntry.eventName === 'PreToolUse' && eachEntry.matcher.split('|').includes(REPLY_MATCHER),
    ));
    assert.ok(shippedEntries.every(eachEntry => isManagedPromptHook(eachEntry.hook)));
});

test('should keep each shipped prompt hook once, under its own event and matcher, after two installs', () => {
    const settings = {};
    mergeHooksIntoSettings(settings, structuredClone(SHIPPED_HOOKS_CONFIG), '/home/example/.claude', 'python3');
    mergeHooksIntoSettings(settings, structuredClone(SHIPPED_HOOKS_CONFIG), '/home/example/.claude', 'python3');

    const placement = eachEntry => `${eachEntry.eventName} ${eachEntry.matcher} ${eachEntry.hook.statusMessage}`;
    assert.deepEqual(
        promptHookEntries(settings).map(placement),
        promptHookEntries(SHIPPED_HOOKS_CONFIG).map(placement),
    );
});
