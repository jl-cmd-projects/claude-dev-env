import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import {
    ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS,
    CLOSING_QUESTION_ROUND_HOOK_RELATIVE_PATH,
    CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH,
} from './install-constants.mjs';

const HOOKS_DIRECTORY = fileURLToPath(new URL('../hooks', import.meta.url));

test('ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS should list the open tasks gate, then the closing question round gate', () => {
    assert.deepEqual(ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS, [
        CURSOR_OPEN_TASKS_HOOK_RELATIVE_PATH,
        CLOSING_QUESTION_ROUND_HOOK_RELATIVE_PATH,
    ]);
    assert.deepEqual(CLOSING_QUESTION_ROUND_HOOK_RELATIVE_PATH, ['blocking', 'closing_question_round_gate.py']);
    assert.ok(Object.isFrozen(ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS));
    assert.ok(Object.isFrozen(CLOSING_QUESTION_ROUND_HOOK_RELATIVE_PATH));
});

test('each profile Stop gate path should name a hook script the package ships', () => {
    const allMissingPaths = ALL_PROFILE_STOP_GATE_HOOK_RELATIVE_PATHS.map(
        relativeParts => path.join(HOOKS_DIRECTORY, ...relativeParts),
    ).filter(scriptPath => !existsSync(scriptPath));
    assert.deepEqual(allMissingPaths, []);
});
