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

test('should own every prompt hook the shipped hooks.json registers, including the claim judge', () => {
    const shippedPromptHooks = Object.values(SHIPPED_HOOKS_CONFIG.hooks)
        .flat()
        .flatMap(eachGroup => eachGroup.hooks.map(eachHook => ({ matcher: eachGroup.matcher, hook: eachHook })))
        .filter(eachEntry => eachEntry.hook.type === 'prompt');

    assert.deepEqual(
        shippedPromptHooks.map(eachEntry => eachEntry.matcher),
        ['mcp__hearthbot__reply|mcp__hearthbot__post_message|mcp__hearthbot__update_message|mcp__hearthbot__ask_decision'],
    );
    assert.deepEqual(shippedPromptHooks.map(eachEntry => isManagedPromptHook(eachEntry.hook)), [true]);
});

test('should keep one shipped claim judge after two installs of the shipped hooks.json', () => {
    const settings = {};
    mergeHooksIntoSettings(settings, SHIPPED_HOOKS_CONFIG, '/home/example/.claude', 'python3');
    mergeHooksIntoSettings(settings, SHIPPED_HOOKS_CONFIG, '/home/example/.claude', 'python3');

    const installedPromptHooks = Object.values(settings.hooks)
        .flat()
        .flatMap(eachGroup => eachGroup.hooks)
        .filter(eachHook => eachHook.type === 'prompt');
    assert.equal(installedPromptHooks.length, 1);
});
