import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
    nativeCursorHooksConfiguration,
    updateCursorHooksFile,
    withOwnedCursorHooks,
    withoutOwnedCursorHooks,
} from './cursor-native-hooks.mjs';

const LEGACY_SESSION_GROUP = {
    matcher: 'startup|resume|clear|compact',
    hooks: [{ type: 'command', command: "'C:\\Users\\dev\\.cursor\\plugins\\deepstack\\hooks\\session-start.sh' cursor" }],
};
const LEGACY_PROMPT_GROUP = {
    matcher: '',
    hooks: [{ type: 'command', command: 'python3 /home/dev/.agents/hooks/session/deepen_first_prompt.py', timeout: 10 }],
};
const USER_TOOL_GROUP = { matcher: 'Shell', hooks: [{ type: 'command', command: './audit.sh' }] };
const isOwned = command => command.includes('plugins/deepstack/hooks/session-start.') || command.includes('deepen_first_prompt.py');

test('Claude-style groups become flat native entries under the Cursor event names', () => {
    const native = nativeCursorHooksConfiguration({
        hooks: { SessionStart: [LEGACY_SESSION_GROUP], UserPromptSubmit: [LEGACY_PROMPT_GROUP], PreToolUse: [USER_TOOL_GROUP] },
    });
    assert.deepEqual(native, {
        version: 1,
        hooks: {
            sessionStart: [{ command: LEGACY_SESSION_GROUP.hooks[0].command }],
            beforeSubmitPrompt: [{ command: LEGACY_PROMPT_GROUP.hooks[0].command, timeout: 10 }],
            preToolUse: [{ command: './audit.sh', matcher: 'Shell' }],
        },
    });
    assert.equal(JSON.stringify(native).includes('"hooks":[{"type"'), false);
});

test('native entries and other fields stay, and the result is stable', () => {
    const configuration = { version: 1, note: 'keep', hooks: { stop: [{ command: './audit.sh', loop_limit: 3 }] } };
    assert.deepEqual(nativeCursorHooksConfiguration(configuration), configuration);
    assert.deepEqual(nativeCursorHooksConfiguration(nativeCursorHooksConfiguration(configuration)), configuration);
});

test('owned entries collapse to one copy and removal drops only owned entries', () => {
    const legacyFile = {
        version: 1,
        hooks: {
            SessionStart: [LEGACY_SESSION_GROUP, LEGACY_SESSION_GROUP, LEGACY_SESSION_GROUP],
            UserPromptSubmit: [LEGACY_PROMPT_GROUP],
            stop: [{ command: './user-stop.sh' }],
        },
    };
    const ownedEntries = {
        sessionStart: [{ command: "'/home/dev/.cursor/plugins/deepstack/hooks/session-start.sh' cursor", timeout: 10 }],
        beforeSubmitPrompt: [{ command: 'python3 /home/dev/.agents/hooks/session/deepen_first_prompt.py', timeout: 10 }],
    };
    const merged = withOwnedCursorHooks(legacyFile, isOwned, ownedEntries);
    assert.deepEqual(merged.hooks, { ...ownedEntries, stop: [{ command: './user-stop.sh' }] });
    assert.deepEqual(withOwnedCursorHooks(merged, isOwned, ownedEntries), merged);
    assert.deepEqual(withoutOwnedCursorHooks(merged, isOwned), { version: 1, hooks: { stop: [{ command: './user-stop.sh' }] } });
});

test('the file update writes only on change, strips a BOM, and creates a file only when asked', () => {
    const cursorDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-native-'));
    try {
        assert.equal(updateCursorHooksFile(cursorDirectory, configuration => configuration), null);
        const hooksPath = updateCursorHooksFile(cursorDirectory, nativeCursorHooksConfiguration, { createWhenMissing: true });
        assert.deepEqual(JSON.parse(readFileSync(hooksPath, 'utf8')), { version: 1, hooks: {} });
        writeFileSync(hooksPath, `\uFEFF${JSON.stringify({ hooks: { Stop: [LEGACY_PROMPT_GROUP] } })}`);
        updateCursorHooksFile(cursorDirectory, nativeCursorHooksConfiguration);
        assert.equal(JSON.parse(readFileSync(hooksPath, 'utf8')).hooks.stop.length, 1);
        assert.equal(updateCursorHooksFile(cursorDirectory, nativeCursorHooksConfiguration), null);
    } finally {
        rmSync(cursorDirectory, { recursive: true, force: true });
    }
});
