import assert from 'node:assert/strict';
import test from 'node:test';

import {
    DEFAULT_INACTIVE_DAYS,
    MILLISECONDS_PER_DAY,
    MILLISECONDS_PER_SECOND,
    PAGE_SIZE,
    REQUEST_TIMEOUT_MILLISECONDS,
    ROLLOUT_FILENAME_PATTERN,
    SOURCE_KINDS,
    THREAD_ID_PATTERN,
} from './constants.mjs';

test('cleanse defaults to a seven-day cutoff and bounded requests', () => {
    assert.equal(DEFAULT_INACTIVE_DAYS, 7);
    assert.equal(MILLISECONDS_PER_DAY, 86_400_000);
    assert.equal(MILLISECONDS_PER_SECOND, 1_000);
    assert.equal(PAGE_SIZE, 1_000);
    assert.equal(REQUEST_TIMEOUT_MILLISECONDS, 30_000);
});

test('session listing includes every supported source kind', () => {
    assert.deepEqual(SOURCE_KINDS, [
        'cli', 'vscode', 'exec', 'appServer', 'subAgent', 'subAgentReview',
        'subAgentCompact', 'subAgentThreadSpawn', 'subAgentOther', 'unknown',
    ]);
});

test('thread IDs accept UUID spelling and reject malformed IDs', () => {
    assert.equal(THREAD_ID_PATTERN.test('12345678-1234-ABCD-1234-123456789ABC'), true);
    assert.equal(THREAD_ID_PATTERN.test('12345678-1234-ABCD-1234-123456789AB'), false);
    assert.equal(THREAD_ID_PATTERN.test('prefix-12345678-1234-ABCD-1234-123456789ABC'), false);
});

test('rollout filenames yield the thread ID and reject other files', () => {
    const threadId = '12345678-1234-ABCD-1234-123456789ABC';
    const filename = `rollout-2026-09-30T12-34-56-${threadId}.jsonl`;
    assert.equal(ROLLOUT_FILENAME_PATTERN.exec(filename)?.[1], threadId);
    assert.equal(ROLLOUT_FILENAME_PATTERN.test(`${filename}.bak`), false);
    assert.equal(ROLLOUT_FILENAME_PATTERN.test(`other-${filename}`), false);
});
