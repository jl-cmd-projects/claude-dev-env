import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import {
    removeAntigravityHooks,
    writeAntigravityHooks,
} from './antigravity-hooks.mjs';

test('writeAntigravityHooks writes managed entry, preserves user entries, and removes cleanly', () => {
    const root = mkdtempSync(join(tmpdir(), 'antigravity-hooks-test-'));
    try {
        const configDir = join(root, '.gemini', 'config');
        const scriptsDir = join(root, '.claude', 'scripts');
        const claudeHome = join(root, '.claude');

        const firstPath = writeAntigravityHooks({
            antigravityConfigDirectory: configDir,
            scriptsDirectory: scriptsDir,
            claudeHomeDirectory: claudeHome,
            pythonCommand: 'python3',
        });
        assert.equal(firstPath, join(configDir, 'hooks.json'));

        const parsed = JSON.parse(readFileSync(firstPath, 'utf8'));
        assert.ok(parsed['claude-dev-env']);
        assert.equal(parsed['claude-dev-env'].SessionStart.length, 1);
        assert.equal(parsed['claude-dev-env'].PreInvocation.length, 1);
        assert.equal(parsed['claude-dev-env'].PreToolUse[0].matcher, '*');
        assert.equal(parsed['claude-dev-env'].PostToolUse[0].matcher, '*');
        assert.equal(parsed['claude-dev-env'].Stop.length, 1);
        assert.match(
            parsed['claude-dev-env'].PreToolUse[0].hooks[0].command,
            /antigravity_hook_bridge\.py['"]? --event PreToolUse --scope global/,
        );

        const secondPath = writeAntigravityHooks({
            antigravityConfigDirectory: configDir,
            scriptsDirectory: scriptsDir,
            claudeHomeDirectory: claudeHome,
            pythonCommand: 'python3',
        });
        assert.equal(secondPath, null);

        parsed['custom-user-hook'] = { Stop: [{ type: 'command', command: 'echo ok' }] };
        writeFileSync(firstPath, `${JSON.stringify(parsed, null, 2)}\n`);

        writeAntigravityHooks({
            antigravityConfigDirectory: configDir,
            scriptsDirectory: scriptsDir,
            claudeHomeDirectory: claudeHome,
            pythonCommand: 'python3',
        });
        const afterRewrite = JSON.parse(readFileSync(firstPath, 'utf8'));
        assert.deepEqual(afterRewrite['custom-user-hook'], parsed['custom-user-hook']);

        const removedPath = removeAntigravityHooks(configDir);
        assert.equal(removedPath, firstPath);
        const afterRemove = JSON.parse(readFileSync(firstPath, 'utf8'));
        assert.equal('claude-dev-env' in afterRemove, false);
        assert.deepEqual(afterRemove['custom-user-hook'], parsed['custom-user-hook']);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});
