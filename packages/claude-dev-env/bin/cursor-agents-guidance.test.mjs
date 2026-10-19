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

const USER_SESSION_GROUP = { matcher: 'startup', hooks: [{ type: 'command', command: 'user-session.sh' }] };

test('merge adds one guidance SessionStart group and one open tasks Stop group and keeps user groups', () => {
    const commands = { guidanceCommand: 'python3 cursor_agents_guidance.py AGENTS.md', openTasksCommand: 'python3 open_tasks_stop_gate.py' };
    const once = mergeCursorAgentsGuidanceHooks({ hooks: { SessionStart: [USER_SESSION_GROUP] } }, commands);
    const twice = mergeCursorAgentsGuidanceHooks(once, commands);
    assert.deepEqual(twice, once);
    assert.deepEqual(twice.hooks.SessionStart[0], USER_SESSION_GROUP);
    assert.equal(twice.hooks.SessionStart.length, 2);
    assert.equal(twice.hooks.Stop.length, 1);
    assert.match(twice.hooks.Stop[0].hooks[0].command, /open_tasks_stop_gate\.py/);
});

test('write registers both hooks with the installed paths and remove takes them out', () => {
    const cursorDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-guidance-'));
    try {
        const hooksPath = join(cursorDirectory, 'hooks.json');
        writeFileSync(hooksPath, JSON.stringify({ hooks: { SessionStart: [USER_SESSION_GROUP] } }));
        const writtenPath = writeCursorAgentsGuidanceHooks({
            cursorDirectory,
            hooksDirectory: '/home/dev/.agents/hooks',
            guidancePath: '/home/dev/.agents/AGENTS.md',
        });
        assert.equal(writtenPath, hooksPath);
        const written = JSON.parse(readFileSync(hooksPath, 'utf8'));
        assert.equal(
            written.hooks.SessionStart[1].hooks[0].command,
            "python3 '/home/dev/.agents/hooks/session/cursor_agents_guidance.py' '/home/dev/.agents/AGENTS.md'",
        );
        assert.equal(written.hooks.Stop[0].hooks[0].command, "python3 '/home/dev/.agents/hooks/blocking/open_tasks_stop_gate.py'");
        assert.equal(writeCursorAgentsGuidanceHooks({
            cursorDirectory,
            hooksDirectory: '/home/dev/.agents/hooks',
            guidancePath: '/home/dev/.agents/AGENTS.md',
        }), null);
        removeCursorAgentsGuidanceHooks(cursorDirectory);
        const removed = JSON.parse(readFileSync(hooksPath, 'utf8'));
        assert.deepEqual(removed.hooks.SessionStart, [USER_SESSION_GROUP]);
        assert.deepEqual(removed.hooks.Stop, []);
    } finally {
        rmSync(cursorDirectory, { recursive: true, force: true });
    }
});

test('write uses the detected interpreter and platform path quoting and sets the schema version', () => {
    const cursorDirectory = mkdtempSync(join(tmpdir(), 'cdev-cursor-guidance-'));
    try {
        writeCursorAgentsGuidanceHooks({
            cursorDirectory,
            hooksDirectory: 'C:/Users/dev/.agents/hooks',
            guidancePath: 'C:/Users/dev/.agents/AGENTS.md',
            pythonCommand: 'C:/Python312/python.exe',
            formatPathArgument: pathValue => `"${pathValue}"`,
        });
        const written = JSON.parse(readFileSync(join(cursorDirectory, 'hooks.json'), 'utf8'));
        assert.equal(written.version, 1);
        assert.equal(
            written.hooks.Stop[0].hooks[0].command,
            'C:/Python312/python.exe "C:/Users/dev/.agents/hooks/blocking/open_tasks_stop_gate.py"',
        );
        assert.match(written.hooks.SessionStart[0].hooks[0].command, /^C:\/Python312\/python\.exe "/);
    } finally {
        rmSync(cursorDirectory, { recursive: true, force: true });
    }
});
