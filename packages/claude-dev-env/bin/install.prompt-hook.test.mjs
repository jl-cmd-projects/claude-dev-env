import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';

import { isManagedPromptHook, mergeHooksIntoSettings, pruneManagedHooksFromSettings } from './install.mjs';

const SHIPPED_HOOKS_CONFIG = JSON.parse(readFileSync(new URL('../hooks/hooks.json', import.meta.url), 'utf8'));

const REPLY_MATCHER = 'mcp__hearthbot__reply';
const EXAMPLE_HOME = '/home/example';
const USER_PROMPT_HOOK = { type: 'prompt', prompt: 'User check. $ARGUMENTS', statusMessage: 'my own check' };

function modelHookEntries(hooksConfig) {
    return Object.entries(hooksConfig.hooks).flatMap(([eventName, matcherGroups]) => matcherGroups.flatMap(
        eachGroup => (eachGroup.hooks ?? [])
            .filter(eachHook => typeof eachHook.command !== 'string')
            .map(eachHook => ({ eventName, matcher: eachGroup.matcher ?? '', hook: eachHook })),
    ));
}

function shippedReplyJudgeEntries() {
    return modelHookEntries(SHIPPED_HOOKS_CONFIG).filter(
        eachEntry => eachEntry.eventName === 'PreToolUse' && eachEntry.matcher.split('|').includes(REPLY_MATCHER),
    );
}

const MANAGED_STATUS = shippedReplyJudgeEntries()[0]?.hook.statusMessage;

function mergeInto(settings, hooksConfig) {
    mergeHooksIntoSettings(settings, hooksConfig, `${EXAMPLE_HOME}/.claude`, 'python3', null, EXAMPLE_HOME);
}

function hooksConfigWithPrompt(promptText) {
    assert.ok(MANAGED_STATUS?.startsWith('claude-dev-env: '), 'the shipped claim judge needs the managed status prefix');
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
        .flatMap(eachGroup => eachGroup.hooks ?? []);
}

test('should keep one managed prompt hook across reinstalls and carry the new prompt text', () => {
    const settings = { hooks: { PreToolUse: [{ matcher: REPLY_MATCHER, hooks: [USER_PROMPT_HOOK] }] } };

    mergeInto(settings, hooksConfigWithPrompt('First judge. $ARGUMENTS'));
    mergeInto(settings, hooksConfigWithPrompt('Second judge. $ARGUMENTS'));

    assert.deepEqual(
        replyHooks(settings).map(eachHook => eachHook.prompt),
        ['User check. $ARGUMENTS', 'Second judge. $ARGUMENTS'],
    );
});

test('should remove the managed prompt hook on uninstall and keep the user prompt hook', () => {
    const settings = { hooks: { PreToolUse: [{ matcher: REPLY_MATCHER, hooks: [USER_PROMPT_HOOK] }] } };
    mergeInto(settings, hooksConfigWithPrompt('Judge. $ARGUMENTS'));

    pruneManagedHooksFromSettings(settings, new Set());

    assert.deepEqual(replyHooks(settings), [USER_PROMPT_HOOK]);
});

test('should mark the shipped claim judge on reply, and any other shipped model hook, as managed', () => {
    assert.ok(shippedReplyJudgeEntries().length > 0);
    assert.ok(modelHookEntries(SHIPPED_HOOKS_CONFIG).every(eachEntry => isManagedPromptHook(eachEntry.hook)));
});

test('should keep the shipped claim judge once, under its own event and matcher, after two installs', () => {
    const settings = {};
    mergeInto(settings, structuredClone(SHIPPED_HOOKS_CONFIG));
    mergeInto(settings, structuredClone(SHIPPED_HOOKS_CONFIG));

    assert.deepEqual(modelHookEntries(settings), modelHookEntries(SHIPPED_HOOKS_CONFIG));
});

test('should drop a managed prompt hook left under a retired matcher of an event the shipped config lists', () => {
    const staleMatcher = 'mcp__hearthbot__retired';
    const judgeOnlyMatcher = 'mcp__hearthbot__retired_alone';
    const oldJudge = { type: 'prompt', prompt: 'Old judge. $ARGUMENTS', statusMessage: MANAGED_STATUS };
    const settings = {
        hooks: {
            PreToolUse: [
                { matcher: staleMatcher, hooks: [oldJudge, USER_PROMPT_HOOK] },
                { matcher: judgeOnlyMatcher, hooks: [oldJudge] },
            ],
        },
    };

    mergeInto(settings, structuredClone(SHIPPED_HOOKS_CONFIG));

    const staleGroup = settings.hooks.PreToolUse.find(eachGroup => eachGroup.matcher === staleMatcher);
    assert.deepEqual(staleGroup.hooks, [USER_PROMPT_HOOK]);
    assert.equal(settings.hooks.PreToolUse.some(eachGroup => eachGroup.matcher === judgeOnlyMatcher), false);
});
