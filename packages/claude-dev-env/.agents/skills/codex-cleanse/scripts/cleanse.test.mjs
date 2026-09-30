import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, renameSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join } from 'node:path';
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

function makeRollout(home, number) {
    const directory = join(home, 'sessions', '2026', '07', '01');
    mkdirSync(directory, { recursive: true });
    const rolloutPath = join(directory, `rollout-2026-07-01T00-00-00-${threadId(number)}.jsonl`);
    writeFileSync(rolloutPath, 'session metadata');
    utimesSync(rolloutPath, new Date(0), new Date(0));
    return rolloutPath;
}

function makeHiddenRequest(home, allThreads, visibleIds, archiveDirectory = join(home, 'archived_sessions')) {
    const archivedIds = new Set();
    const allCalls = [];
    const request = async (method, params) => {
        allCalls.push({ method, params });
        if (method === 'thread/read') {
            return { thread: allThreads.find(eachThread => eachThread.id === params.threadId) };
        }
        if (method === 'thread/archive') {
            const thread = allThreads.find(eachThread => eachThread.id === params.threadId);
            mkdirSync(archiveDirectory, { recursive: true });
            const archivedPath = join(archiveDirectory, basename(thread.path));
            renameSync(thread.path, archivedPath);
            thread.path = archivedPath;
            archivedIds.add(thread.id);
            return {};
        }
        const matchingThreads = allThreads.filter(eachThread =>
            archivedIds.has(eachThread.id) === params.archived
            && (params.ancestorThreadId
                ? eachThread.parentThreadId === params.ancestorThreadId
                : visibleIds.has(eachThread.id)));
        return { data: matchingThreads, nextCursor: null };
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
        writeFileSync(rolloutPath, 'session metadata');
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

test('apply reads back earlier archives and stops after a rejected archive', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = join(directory, 'rollout.jsonl');
        writeFileSync(rolloutPath, 'session metadata');
        utimesSync(rolloutPath, new Date(0), new Date(0));
        const allThreads = [1, 2, 3].map(number => makeThread(number, cutoff - 1, { path: rolloutPath }));
        const fixture = makeRequest(allThreads, new Set([threadId(2)]), new Set([threadId(1)]));
        const report = await cleanseSessions(fixture.request, makeOptions({ apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [threadId(2), threadId(1)]);
        assert.deepEqual(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive')
            .map(eachCall => eachCall.params.threadId), [threadId(1), threadId(2)]);
        assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/read'
            && eachCall.params.threadId === threadId(1)).length, 2);
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
        writeFileSync(rolloutPath, 'session metadata');
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

test('uppercase CLI exclusion is stored as a lowercase UUID', () => {
    const uppercaseId = 'ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF';
    const options = parseOptions(['--exclude-thread-id', uppercaseId]);
    assert.deepEqual([...options.excludedThreadIds], [uppercaseId.toLowerCase()]);
});

test('lowercase exclusion protects a native thread with an uppercase UUID', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const uppercaseId = 'ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF';
        const options = parseOptions(['--codex-home', home, '--exclude-thread-id', uppercaseId.toLowerCase(), '--apply']);
        const fixture = makeRequest([makeThread(1, cutoff - 1, { id: uppercaseId })]);
        const report = await cleanseSessions(fixture.request, options, now);
        assert.equal(report.skippedReasons.excluded, 1);
        assert.equal(report.archived, 0);
        assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('apply finds an old hidden child and archives it before its visible parent', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const parent = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        const child = makeThread(2, cutoff - 1, { path: makeRollout(home, 2), parentThreadId: parent.id });
        const fixture = makeHiddenRequest(home, [parent, child], new Set([parent.id]));
        const report = await cleanseSessions(fixture.request, makeOptions({ home, apply: true }), now);
        assert.equal(report.scanned, 2);
        assert.equal(report.archived, 2);
        assert.deepEqual(report.failed, []);
        assert.deepEqual(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive')
            .map(eachCall => eachCall.params.threadId), [child.id, parent.id]);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('apply archives an old hidden orphan from the selected home only', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    const otherHome = mkdtempSync(join(tmpdir(), 'codex-cleanse-other-'));
    try {
        const orphan = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        writeFileSync(join(home, 'sessions', 'notes.jsonl'), 'ignored');
        makeRollout(otherHome, 2);
        const fixture = makeHiddenRequest(home, [orphan], new Set());
        const report = await cleanseSessions(fixture.request, makeOptions({ home, apply: true }), now);
        assert.equal(report.scanned, 1);
        assert.equal(report.archived, 1);
        assert.deepEqual(report.failed, []);
    } finally {
        rmSync(home, { recursive: true, force: true });
        rmSync(otherHome, { recursive: true, force: true });
    }
});

test('a recent hidden child keeps its old parent unarchived', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const parent = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        const child = makeThread(2, cutoff + 1, { path: makeRollout(home, 2), parentThreadId: parent.id });
        const fixture = makeHiddenRequest(home, [parent, child], new Set([parent.id]));
        const report = await cleanseSessions(fixture.request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 0);
        assert.equal(report.skippedReasons.descendant, 1);
        assert.equal(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('hidden discovery reports native ID and path mismatches', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = makeRollout(home, 1);
        const wrongPath = makeRollout(home, 2);
        for (const thread of [makeThread(2, cutoff - 1, { path: rolloutPath }),
            makeThread(1, cutoff - 1, { path: wrongPath })]) {
            const request = async (method, params) => method === 'thread/read'
                ? { thread }
                : { data: [], nextCursor: null };
            const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
            assert.equal(report.archived, 0);
            assert.ok(report.failed.some(eachFailure => eachFailure.id === threadId(1)));
        }
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('hidden discovery reports a native read failure', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        makeRollout(home, 1);
        const request = async (method, params) => {
            if (method === 'thread/read') throw new Error('native read failed');
            return { data: [], nextCursor: null };
        };
        const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [threadId(1)]);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('a hidden child read failure stops its listed parent before archive', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const parent = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        makeRollout(home, 2);
        const allCalls = [];
        const request = async (method, params) => {
            allCalls.push({ method, params });
            if (method === 'thread/list') {
                return { data: params.ancestorThreadId ? [] : [parent], nextCursor: null };
            }
            if (method === 'thread/read' && params.threadId === threadId(2)) {
                throw new Error('Hidden child metadata unreadable');
            }
            if (method === 'thread/read') return { thread: parent };
            return {};
        };
        const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [threadId(2)]);
        assert.equal(allCalls.filter(eachCall => eachCall.method === 'thread/archive').length, 0);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('a hidden child archive failure stops its listed parent with an incomplete ancestor listing', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const parent = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        const child = makeThread(2, cutoff - 1, { path: makeRollout(home, 2), parentThreadId: parent.id });
        const fixture = makeHiddenRequest(home, [parent, child], new Set([parent.id]));
        const request = async (method, params) => {
            if (method === 'thread/list' && params.ancestorThreadId) {
                return { data: [], nextCursor: null };
            }
            if (method === 'thread/archive' && params.threadId === child.id) {
                fixture.allCalls.push({ method, params });
                throw new Error('child archive rejected');
            }
            return fixture.request(method, params);
        };
        const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [child.id]);
        assert.deepEqual(fixture.allCalls.filter(eachCall => eachCall.method === 'thread/archive')
            .map(eachCall => eachCall.params.threadId), [child.id]);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('empty rollout stubs skip native read and archive', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const rolloutPath = makeRollout(home, 1);
        writeFileSync(rolloutPath, '');
        const allMethods = [];
        const request = async method => {
            allMethods.push(method);
            if (method !== 'thread/list') throw new Error('Empty rollout reached native session API');
            return { data: [], nextCursor: null };
        };
        const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
        assert.equal(report.scanned, 1);
        assert.equal(report.skippedReasons.emptyRollout, 1);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed, []);
        assert.deepEqual(allMethods, ['thread/list']);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('hidden archive readback rejects a sibling directory with the archived name prefix', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const orphan = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        const siblingDirectory = join(home, 'archived_sessions-copy');
        const fixture = makeHiddenRequest(home, [orphan], new Set(), siblingDirectory);
        const report = await cleanseSessions(fixture.request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 0);
        assert.deepEqual(report.failed.map(eachFailure => eachFailure.id), [orphan.id]);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});

test('hidden discovery and readback accept paths that resolve to the same rollout file', async () => {
    const home = mkdtempSync(join(tmpdir(), 'codex-cleanse-'));
    try {
        const orphan = makeThread(1, cutoff - 1, { path: makeRollout(home, 1) });
        orphan.path = process.platform === 'win32'
            ? `\\\\?\\${orphan.path}`
            : join(dirname(orphan.path), '..', '01', basename(orphan.path));
        const fixture = makeHiddenRequest(home, [orphan], new Set());
        const request = async (method, params) => {
            const reply = await fixture.request(method, params);
            if (method === 'thread/archive' && process.platform === 'win32') {
                orphan.path = `\\\\?\\${orphan.path}`;
            }
            return reply;
        };
        const report = await cleanseSessions(request, makeOptions({ home, apply: true }), now);
        assert.equal(report.archived, 1);
        assert.deepEqual(report.failed, []);
    } finally {
        rmSync(home, { recursive: true, force: true });
    }
});
