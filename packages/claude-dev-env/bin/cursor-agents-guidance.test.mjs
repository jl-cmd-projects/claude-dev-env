import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
    mergeCursorAgentsGuidanceHooks,
    removeCursorAgentsGuidanceHooks,
    writeCursorAgentsGuidanceHooks,
} from './cursor-agents-guidance.mjs';

const USER_SESSION_ENTRY = { command: './user-session.sh' };
const LEGACY_GUIDANCE_GROUP = {
    matcher: 'startup|resume|clear|compact',
    hooks: [{ type: 'command', command: "python3 '/home/dev/.agents/hooks/session/cursor_agents_guidance.py' AGENTS.md", timeout: 10 }],
};
const LEGACY_GATE_GROUP = {
    matcher: '',
    hooks: [{ type: 'command', command: "python3 '/home/dev/.agents/hooks/blocking/open_tasks_stop_gate.py'", timeout: 10 }],
};

test('merge adds one native sessionStart entry and one native stop entry and keeps user entries', () => {
    const commands = { guidanceCommand: 'python3 cursor_agents_guidance.py AGENTS.md', openTasksCommand: 'python3 open_tasks_stop_gate.py' };
    const once = mergeCursorAgentsGuidanceHooks({ hooks: { sessionStart: [USER_SESSION_ENTRY] } }, commands);
    assert.deepEqual(mergeCursorAgentsGuidanceHooks(once, commands), once);
    assert.deepEqual(once, {
        version: 1,
        hooks: {
            sessionStart: [USER_SESSION_ENTRY, { command: commands.guidanceCommand, timeout: 10 }],
            stop: [{ command: commands.openTasksCommand, timeout: 10 }],
        },
    });
});

test('merge replaces the Claude-style groups an earlier build of this module wrote', () => {
    const commands = { guidanceCommand: 'py cursor_agents_guidance.py AGENTS.md', openTasksCommand: 'py open_tasks_stop_gate.py' };
    const merged = mergeCursorAgentsGuidanceHooks(
        { hooks: { SessionStart: [LEGACY_GUIDANCE_GROUP], Stop: [LEGACY_GATE_GROUP] } },
        commands,
    );
    assert.deepEqual(Object.keys(merged.hooks), ['sessionStart', 'stop']);
    assert.equal(merged.hooks.sessionStart.length, 1);
    assert.equal(merged.hooks.stop.length, 1);
    assert.equal(merged.hooks.stop[0].command, commands.openTasksCommand);
});

test('write registers both hooks with the installed paths and remove takes out exactly those', () => {
    const cursorDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-guidance-'));
    try {
        const hooksPath = join(cursorDirectory, 'hooks.json');
        writeFileSync(hooksPath, JSON.stringify({ version: 1, hooks: { sessionStart: [USER_SESSION_ENTRY] } }));
        const installOptions = {
            cursorDirectory,
            hooksDirectory: '/home/dev/.agents/hooks',
            guidancePath: '/home/dev/.agents/AGENTS.md',
        };
        assert.equal(writeCursorAgentsGuidanceHooks(installOptions), hooksPath);
        const written = JSON.parse(readFileSync(hooksPath, 'utf8'));
        const guidanceScript = join(installOptions.hooksDirectory, 'session', 'cursor_agents_guidance.py');
        const openTasksScript = join(installOptions.hooksDirectory, 'blocking', 'open_tasks_stop_gate.py');
        assert.equal(
            written.hooks.sessionStart[1].command,
            `python3 '${guidanceScript}' '/home/dev/.agents/AGENTS.md'`,
        );
        assert.equal(written.hooks.stop[0].command, `python3 '${openTasksScript}'`);
        assert.equal(writeCursorAgentsGuidanceHooks(installOptions), null);
        removeCursorAgentsGuidanceHooks(cursorDirectory);
        assert.deepEqual(JSON.parse(readFileSync(hooksPath, 'utf8')), { version: 1, hooks: { sessionStart: [USER_SESSION_ENTRY] } });
    } finally {
        rmSync(cursorDirectory, { recursive: true, force: true });
    }
});

test('write uses the detected interpreter and platform path quoting and sets the schema version', () => {
    const cursorDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-guidance-'));
    try {
        const hooksDirectory = 'C:/Users/dev/.agents/hooks';
        writeCursorAgentsGuidanceHooks({
            cursorDirectory,
            hooksDirectory,
            guidancePath: 'C:/Users/dev/.agents/AGENTS.md',
            pythonCommand: 'C:/Python312/python.exe',
            formatPathArgument: pathValue => `"${pathValue}"`,
        });
        const written = JSON.parse(readFileSync(join(cursorDirectory, 'hooks.json'), 'utf8'));
        assert.equal(written.version, 1);
        const openTasksScript = join(hooksDirectory, 'blocking', 'open_tasks_stop_gate.py');
        assert.equal(written.hooks.stop[0].command, `C:/Python312/python.exe "${openTasksScript}"`);
        assert.match(written.hooks.sessionStart[0].command, /^C:\/Python312\/python\.exe "/);
    } finally {
        rmSync(cursorDirectory, { recursive: true, force: true });
    }
});
