import { test } from 'node:test';
import { strict as assert } from 'node:assert';

import { mergeHooksIntoSettings, pruneManagedHooksFromSettings } from './install.mjs';

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
