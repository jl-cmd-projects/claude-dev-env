import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { assertSelectedHome, cleanseSessions, parseOptions } from './cleanse.mjs';

const now = Date.parse('2026-09-30T12:00:00.000Z');
const cutoff = Math.floor((now - 7 * 86_400_000) / 1_000);
const threadId = number => `00000000-0000-4000-8000-${String(number).padStart(12, '0')}`;

function makeThread(number, updatedAt, overrides = {}) {
    return {
        id: threadId(number),
        updatedAt,
        status: { type: 'idle' },
        parentThreadId: null,
        ephemeral: false,
        ...overrides,
    };
}

function makeOptions(overrides = {}) {
    return {
        home: join(tmpdir(), 'account-a'),
        inactiveDays: 7,
        apply: false,
        excludedThreadIds: new Set(),
        ...overrides,
    };
}

function makeRequest(allThreads, archiveFailures = new Set(), missingReadback = new Set()) {
    const archivedIds = new Set();
    const allCalls = [];
    const request = async (method, params) => {
        allCalls.push({ method, params });
        if (method === 'thread/list') {
            const selectedThreads = allThreads.filter(eachThread =>
                params.archived === archivedIds.has(eachThread.id)
                && (!params.ancestorThreadId || eachThread.parentThreadId === params.ancestorThreadId)
                && (!params.archived || !missingReadback.has(eachThread.id)));
            const offset = Number(params.cursor || 0);
            return { data: selectedThreads.slice(offset, offset + 2), nextCursor: offset + 2 < selectedThreads.length ? String(offset + 2) : null };
        }
        if (method === 'thread/read') {
            return { thread: allThreads.find(eachThread => eachThread.id === params.threadId) };
        }
        if (method === 'thread/archive') {
            if (archiveFailures.has(params.threadId)) throw new Error('archive rejected');
            archivedIds.add(params.threadId);
            return {};
        }
        throw new Error(`Unexpected method: ${method}`);
    };
    return { request, allCalls, archivedIds };
}

test('preview counts every page and source without archiving', async () => {
    const allThreads = [
        makeThread(1, cutoff),
        makeThread(2, cutoff - 1),
        makeThread(3, cutoff + 1),
    ];
    const fixture = makeRequest(allThreads);
    const report = await cleanseSessions(fixture.request, makeOptions(), now);
    assert.deepEqual([report.scanned, report.eligible, report.skipped, report.archived], [3, 2, 1, 0]);
    assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/list').length, 2);
    assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
});

test('preview protects running sessions, excluded IDs, and parents with recent children', async () => {
    const allThreads = [
        makeThread(1, cutoff - 1, { status: { type: 'active' } }),
        makeThread(2, cutoff - 1),
        makeThread(3, cutoff - 1),
        makeThread(4, cutoff + 1, { parentThreadId: threadId(3) }),
        makeThread(5, cutoff - 1, { updatedAt: 0 }),
    ];
    const fixture = makeRequest(allThreads);
    const options = makeOptions({ excludedThreadIds: new Set([threadId(2)]) });
    const report = await cleanseSessions(fixture.request, options, now);
    assert.equal(report.eligible, 0);
    assert.equal(report.skipped, 5);
});

test('apply archives a stale leaf and confirms archived listing', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = join(directory, 'rollout.jsonl');
        writeFileSync(rolloutPath, '');
        utimesSync(rolloutPath, new Date(0), new Date(0));
        const fixture = makeRequest([makeThread(1, cutoff - 1, { path: rolloutPath })]);
        const report = await cleanseSessions(fixture.request, makeOptions({ apply: true }), now);
        assert.equal(report.archived, 1);
        assert.deepEqual(report.failed, []);
        assert.deepEqual([...fixture.archivedIds], [threadId(1)]);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

test('apply archives a stale database-backed thread with no rollout path', async () => {
    const fixture = makeRequest([makeThread(1, cutoff - 1, { path: null })]);
    const report = await cleanseSessions(fixture.request, makeOptions({ apply: true }), now);
    assert.equal(report.archived, 1);
    assert.deepEqual(report.failed, []);
});

test('apply reports a rejected archive and a missing readback by ID', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = join(directory, 'rollout.jsonl');
        writeFileSync(rolloutPath, '');
        utimesSync(rolloutPath, new Date(0), new Date(0));
        const allThreads = [makeThread(1, cutoff - 1, { path: rolloutPath }), makeThread(2, cutoff - 1, { path: rolloutPath })];
        const fixture = makeRequest(allThreads, new Set([threadId(1)]), new Set([threadId(2)]));
        const report = await cleanseSessions(fixture.request, makeOptions({ apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [threadId(1), threadId(2)]);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

test('apply skips a rollout file changed after the cutoff', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = join(directory, 'rollout.jsonl');
        writeFileSync(rolloutPath, 'new activity');
        const fixture = makeRequest([makeThread(1, cutoff - 1, { path: rolloutPath })]);
        const report = await cleanseSessions(fixture.request, makeOptions({ apply: true }), now);
        assert.equal(report.archived, 0);
        assert.equal(report.skippedReasons.recentRolloutWrite, 1);
        assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

test('apply protects a parent when the daemon finds a recent descendant absent from parent metadata', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = join(directory, 'rollout.jsonl');
        writeFileSync(rolloutPath, '');
        utimesSync(rolloutPath, new Date(0), new Date(0));
        const parent = makeThread(1, cutoff - 1, { path: rolloutPath });
        const child = makeThread(2, cutoff + 1);
        const fixture = makeRequest([parent, child]);
        const request = async (method, params) => {
            if (method === 'thread/list' && params.ancestorThreadId === parent.id) {
                return { data: [child], nextCursor: null };
            }
            return fixture.request(method, params);
        };
        const report = await cleanseSessions(request, makeOptions({ apply: true }), now);
        assert.equal(report.archived, 0);
        assert.equal(report.skippedReasons.descendant, 1);
        assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

test('selected Codex home follows the flag before the environment and rejects a mismatched server', () => {
    const homeFromEnvironment = join(tmpdir(), 'account-a');
    const homeFromFlag = join(tmpdir(), 'account-b');
    const options = parseOptions(['--codex-home', homeFromFlag], { CODEX_HOME: homeFromEnvironment });
    assert.equal(options.home, homeFromFlag);
    assert.doesNotThrow(() => assertSelectedHome(homeFromFlag, options.home));
    assert.throws(() => assertSelectedHome(homeFromEnvironment, options.home), /differs from selected home/);
});

test('every value-taking option rejects a following flag or end of arguments', () => {
    const allValueTakingFlags = ['--inactive-days', '--codex-home', '--codex-path', '--exclude-thread-id'];
    for (const eachFlag of allValueTakingFlags) {
        assert.throws(() => parseOptions([eachFlag, '--apply']), new RegExp(`Missing value for ${eachFlag}`));
        assert.throws(() => parseOptions([eachFlag]), new RegExp(`Missing value for ${eachFlag}`));
    }
});
