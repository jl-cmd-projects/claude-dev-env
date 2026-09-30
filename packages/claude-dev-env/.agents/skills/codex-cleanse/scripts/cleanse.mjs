import { spawn } from 'node:child_process';
import { accessSync, constants, existsSync, lstatSync, readdirSync, realpathSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, delimiter, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

import {
    DEFAULT_INACTIVE_DAYS,
    MILLISECONDS_PER_DAY,
    MILLISECONDS_PER_SECOND,
    PAGE_SIZE,
    REQUEST_TIMEOUT_MILLISECONDS,
    ROLLOUT_FILENAME_PATTERN,
    SOURCE_KINDS,
    THREAD_ID_PATTERN,
} from '../config/constants.mjs';

const scriptPath = fileURLToPath(import.meta.url);

export function parseOptions(allArguments, environment = process.env) {
    const options = {
        apply: false,
        inactiveDays: DEFAULT_INACTIVE_DAYS,
        home: resolve(environment.CODEX_HOME || join(homedir(), '.codex')),
        codexPath: null,
        excludedThreadIds: new Set(),
    };
    for (let index = 0; index < allArguments.length; index += 1) {
        const argument = allArguments[index];
        if (argument === '--apply') {
            options.apply = true;
            continue;
        }
        if (argument === '--stdio') {
            continue;
        }
        const argumentValue = allArguments[++index];
        if (!argumentValue || argumentValue.startsWith('--')) throw new Error(`Missing value for ${argument}`);
        if (argument === '--inactive-days') options.inactiveDays = Number(argumentValue);
        else if (argument === '--codex-home') options.home = resolve(argumentValue);
        else if (argument === '--codex-path') options.codexPath = resolve(argumentValue);
        else if (argument === '--exclude-thread-id') options.excludedThreadIds.add(argumentValue.toLowerCase());
        else throw new Error(`Unknown option: ${argument}`);
    }
    if (!Number.isFinite(options.inactiveDays) || options.inactiveDays < 0) {
        throw new Error('--inactive-days must be a nonnegative number');
    }
    if (Number.isNaN(new Date(Date.now() - options.inactiveDays * MILLISECONDS_PER_DAY).getTime())) {
        throw new Error('--inactive-days must produce a valid cutoff date');
    }
    for (const eachThreadId of options.excludedThreadIds) {
        if (!THREAD_ID_PATTERN.test(eachThreadId)) throw new Error('Invalid excluded thread ID');
    }
    return options;
}

export function assertSelectedHome(serverHome, selectedHome) {
    try {
        if (serverHome && isSameCanonicalPath(serverHome, selectedHome)) return;
    } catch (error) {
        throw new Error('Codex server home differs from selected home', { cause: error });
    }
    throw new Error('Codex server home differs from selected home');
}

function isExecutableFile(executablePath) {
    try {
        if (!statSync(executablePath).isFile()) return false;
        accessSync(executablePath, constants.X_OK);
        return true;
    } catch {
        return false;
    }
}

export function findCodexPath(options, environment = process.env) {
    if (options.codexPath) {
        if (!existsSync(options.codexPath)) throw new Error(`Codex executable not found: ${options.codexPath}`);
        return options.codexPath;
    }
    const executableName = process.platform === 'win32' ? 'codex.exe' : 'codex';
    const allCandidates = [
        environment.APPDATA && join(environment.APPDATA, 'npm', 'node_modules', '@openai', 'codex',
            'node_modules', '@openai', 'codex-win32-x64', 'vendor', 'x86_64-pc-windows-msvc', 'bin', executableName),
        join(options.home, 'packages', 'standalone', 'current', 'bin', executableName),
        environment.LOCALAPPDATA && join(environment.LOCALAPPDATA, 'Programs', 'OpenAI', 'Codex', 'bin', executableName),
    ].filter(Boolean);
    const pathKey = process.platform === 'win32'
        ? Object.keys(environment).find(eachKey => eachKey.toUpperCase() === 'PATH') : 'PATH';
    for (const eachDirectory of (environment[pathKey] || '').split(delimiter).filter(Boolean)) {
        allCandidates.push(join(eachDirectory, executableName));
        if (process.platform === 'win32') {
            allCandidates.push(join(eachDirectory, 'node_modules', '@openai', 'codex',
                'node_modules', '@openai', 'codex-win32-x64', 'vendor', 'x86_64-pc-windows-msvc', 'bin', executableName));
        }
    }
    const codexPath = allCandidates.find(isExecutableFile);
    if (!codexPath) throw new Error('Codex executable not found; pass --codex-path');
    return codexPath;
}

export function openDaemon(options, environment = process.env) {
    const codexPath = findCodexPath(options, environment);
    const child = spawn(codexPath, ['app-server'], {
        env: { ...environment, CODEX_HOME: options.home },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
    });
    const pendingById = new Map();
    let nextId = 1;
    let transportFailure = null;
    let stderrTail = '';
    const failPending = error => {
        transportFailure = error;
        for (const { reject, timer } of pendingById.values()) {
            clearTimeout(timer);
            reject(error);
        }
        pendingById.clear();
    };
    createInterface({ input: child.stdout }).on('line', line => {
        let message;
        try { message = JSON.parse(line); } catch { return; }
        const pending = pendingById.get(message.id);
        if (!pending) return;
        clearTimeout(pending.timer);
        pendingById.delete(message.id);
        if (message.error) pending.reject(new Error(JSON.stringify(message.error)));
        else pending.resolve(message.result);
    });
    child.stderr.on('data', chunk => { stderrTail = `${stderrTail}${chunk}`.slice(-2_000); });
    child.stdin.on('error', failPending);
    child.on('error', failPending);
    child.on('exit', code => failPending(new Error(`Codex daemon proxy exited with code ${code}`)));
    const request = (method, params = {}) => {
        if (transportFailure) return Promise.reject(transportFailure);
        const id = nextId++;
        return new Promise((resolveRequest, rejectRequest) => {
            const timer = setTimeout(() => {
                failPending(new Error(`Codex daemon request timed out: ${method}; ${stderrTail.trim()}`));
            }, REQUEST_TIMEOUT_MILLISECONDS);
            pendingById.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
            child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
        });
    };
    return {
        request,
        async initialize() {
            const handshake = await request('initialize', {
                clientInfo: { name: 'codex_cleanse', title: 'Codex Cleanse', version: '1.0.0' },
                capabilities: { experimentalApi: true },
            });
            assertSelectedHome(handshake?.codexHome, options.home);
            child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method: 'initialized', params: {} })}\n`);
        },
        close() {
            child.stdin.end();
            setTimeout(() => { if (child.exitCode === null) child.kill(); }, 2_000).unref();
        },
        isHealthy() { return !transportFailure; },
    };
}

async function listThreads(request, archived, filters = {}) {
    const allThreads = [];
    const allCursors = new Set();
    let cursor = null;
    let pageCount = 0;
    do {
        const page = await request('thread/list', {
            limit: PAGE_SIZE,
            archived,
            useStateDbOnly: true,
            sourceKinds: SOURCE_KINDS,
            sortKey: 'updated_at',
            sortDirection: 'desc',
            ...filters,
            ...(cursor && { cursor }),
        });
        if (!Array.isArray(page?.data)) throw new Error('Invalid thread/list reply');
        allThreads.push(...page.data);
        pageCount += 1;
        if (pageCount % 10 === 0) process.stderr.write(`Listed ${allThreads.length} threads\n`);
        cursor = page.nextCursor;
        if (cursor && allCursors.has(cursor)) throw new Error('Repeated thread/list cursor');
        if (cursor) allCursors.add(cursor);
    } while (cursor);
    return allThreads;
}

function discoverRolloutPaths(home) {
    const sessionsDirectory = join(home, 'sessions');
    const pathById = new Map();
    const failures = [];
    const allDirectories = [sessionsDirectory];
    try {
        if (!lstatSync(sessionsDirectory).isDirectory()) throw new Error('Sessions path is not a directory');
    } catch (error) {
        if (error.code === 'ENOENT') return { pathById, failures };
        return { pathById, failures: [{ id: null, error: String(error.message || error) }] };
    }
    while (allDirectories.length) {
        const directory = allDirectories.pop();
        let allEntries;
        try { allEntries = readdirSync(directory, { withFileTypes: true }); }
        catch (error) {
            failures.push({ id: null, error: String(error.message || error) });
            continue;
        }
        for (const eachEntry of allEntries) {
            if (eachEntry.isSymbolicLink()) continue;
            const entryPath = join(directory, eachEntry.name);
            if (eachEntry.isDirectory()) allDirectories.push(entryPath);
            if (!eachEntry.isFile()) continue;
            const threadId = ROLLOUT_FILENAME_PATTERN.exec(eachEntry.name)?.[1]?.toLowerCase();
            if (!threadId) continue;
            if (pathById.has(threadId)) {
                failures.push({ id: threadId, error: 'Duplicate rollout ID under sessions' });
                continue;
            }
            pathById.set(threadId, entryPath);
        }
    }
    return { pathById, failures };
}

function isSameCanonicalPath(leftPath, rightPath) {
    const left = realpathSync.native(leftPath);
    const right = realpathSync.native(rightPath);
    return process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;
}

async function discoverHiddenThreads(request, home, listedThreads, isHealthy) {
    const { pathById, failures } = discoverRolloutPaths(home);
    const listedIds = new Set(listedThreads.map(eachThread => eachThread.id.toLowerCase()));
    const hiddenThreads = [];
    let emptyRolloutCount = 0;
    for (const [eachThreadId, rolloutPath] of pathById) {
        if (listedIds.has(eachThreadId)) continue;
        try {
            if (statSync(rolloutPath).size === 0) {
                emptyRolloutCount += 1;
                continue;
            }
            const thread = (await request('thread/read', { threadId: eachThreadId, includeTurns: false })).thread;
            if (thread?.id?.toLowerCase() !== eachThreadId || !thread.path
                || !isSameCanonicalPath(thread.path, rolloutPath)) {
                throw new Error('Native thread metadata differs from discovered rollout');
            }
            hiddenThreads.push(thread);
        } catch (error) {
            failures.push({ id: eachThreadId, error: String(error.message || error) });
            if (!isHealthy()) break;
        }
    }
    return { hiddenThreads, failures, emptyRolloutCount };
}

function isArchivedReadback(thread, threadId, home) {
    if (thread?.id !== threadId || !thread.path) return false;
    if (ROLLOUT_FILENAME_PATTERN.exec(basename(thread.path))?.[1]?.toLowerCase() !== threadId.toLowerCase()) return false;
    try {
        const archiveDirectory = realpathSync.native(join(home, 'archived_sessions'));
        const archivedPath = realpathSync.native(thread.path);
        const pathWithinArchive = relative(archiveDirectory, archivedPath);
        return pathWithinArchive !== '' && pathWithinArchive !== '..'
            && !pathWithinArchive.startsWith(`..${sep}`) && !isAbsolute(pathWithinArchive)
            && statSync(archivedPath).isFile();
    } catch {
        return false;
    }
}

function ineligibilityReason(thread, cutoffSeconds, excludedThreadIds) {
    if (!THREAD_ID_PATTERN.test(thread?.id)) return 'invalidId';
    if (excludedThreadIds.has(thread.id.toLowerCase())) return 'excluded';
    if (thread.ephemeral) return 'ephemeral';
    if (!Number.isSafeInteger(thread.updatedAt) || thread.updatedAt <= 0) return 'unknownActivity';
    if (thread.updatedAt > cutoffSeconds) return 'recent';
    if (thread.status?.type === 'active') return 'active';
    if (!['idle', 'notLoaded'].includes(thread.status?.type)) return 'unknownStatus';
    return null;
}

function rolloutWriteReason(thread, cutoffMilliseconds) {
    if (!thread.path) return null;
    try {
        const fileStatus = statSync(thread.path);
        if (fileStatus.size === 0) return 'emptyRollout';
        return fileStatus.mtimeMs > cutoffMilliseconds ? 'recentRolloutWrite' : null;
    } catch {
        return 'missingRollout';
    }
}

function candidateReason(thread, cutoffSeconds, excludedThreadIds) {
    return ineligibilityReason(thread, cutoffSeconds, excludedThreadIds)
        || rolloutWriteReason(thread, cutoffSeconds * MILLISECONDS_PER_SECOND);
}

function parentThreadId(thread) {
    return thread.parentThreadId || thread.source?.subAgent?.thread_spawn?.parent_thread_id;
}

function sortChildrenBeforeParents(allThreads) {
    const threadById = new Map(allThreads.map(eachThread => [eachThread.id, eachThread]));
    const depthById = new Map();
    const depthOf = (thread, visited = new Set()) => {
        if (depthById.has(thread.id)) return depthById.get(thread.id);
        if (visited.has(thread.id)) throw new Error('Thread parent cycle');
        visited.add(thread.id);
        const parent = threadById.get(parentThreadId(thread));
        const depth = parent ? depthOf(parent, visited) + 1 : 0;
        depthById.set(thread.id, depth);
        visited.delete(thread.id);
        return depth;
    };
    return [...allThreads].sort((left, right) => depthOf(right) - depthOf(left));
}

function findProtectedAncestors(allThreads, cutoffSeconds, excludedThreadIds) {
    const threadById = new Map(allThreads.map(eachThread => [eachThread.id, eachThread]));
    const protectedIds = new Set();
    for (const eachThread of allThreads) {
        if (!candidateReason(eachThread, cutoffSeconds, excludedThreadIds)) continue;
        let parentId = parentThreadId(eachThread);
        while (parentId && !protectedIds.has(parentId)) {
            protectedIds.add(parentId);
            const parent = threadById.get(parentId);
            parentId = parent && parentThreadId(parent);
        }
    }
    return protectedIds;
}

function createReport(options, cutoffSeconds) {
    return {
        home: options.home,
        cutoff: new Date(cutoffSeconds * MILLISECONDS_PER_SECOND).toISOString(),
        scanned: 0,
        eligible: 0,
        archived: 0,
        skipped: 0,
        skippedReasons: {},
        failed: [],
    };
}

export async function cleanseSessions(request, options, now = Date.now(), isHealthy = () => true) {
    const cutoffSeconds = Math.floor((now - options.inactiveDays * MILLISECONDS_PER_DAY) / MILLISECONDS_PER_SECOND);
    const report = createReport(options, cutoffSeconds);
    let listedThreads;
    try {
        listedThreads = await listThreads(request, false);
    } catch (error) {
        report.failed.push({ id: null, error: String(error.message || error) });
        return report;
    }
    const { hiddenThreads, failures, emptyRolloutCount } = await discoverHiddenThreads(
        request, options.home, listedThreads, isHealthy);
    const allThreads = [...hiddenThreads, ...listedThreads];
    report.scanned = allThreads.length + emptyRolloutCount;
    report.skipped = emptyRolloutCount;
    report.skippedReasons = emptyRolloutCount ? { emptyRollout: emptyRolloutCount } : {};
    report.failed = failures;
    const recordSkip = reason => {
        report.skipped += 1;
        report.skippedReasons[reason] = (report.skippedReasons[reason] || 0) + 1;
    };
    const protectedIds = findProtectedAncestors(allThreads, cutoffSeconds, options.excludedThreadIds);
    if (!options.apply) {
        for (const eachThread of allThreads) {
            const reason = candidateReason(eachThread, cutoffSeconds, options.excludedThreadIds);
            if (reason || protectedIds.has(eachThread.id)) recordSkip(reason || 'descendant');
            else report.eligible += 1;
        }
        return report;
    }
    if (report.failed.length) return report;
    const allAttemptedArchiveIds = [];
    for (const eachThread of sortChildrenBeforeParents(allThreads)) {
        if (report.failed.length) break;
        const reason = candidateReason(eachThread, cutoffSeconds, options.excludedThreadIds);
        if (reason || protectedIds.has(eachThread.id)) {
            recordSkip(reason || 'descendant');
            continue;
        }
        try {
            const freshThread = (await request('thread/read', { threadId: eachThread.id, includeTurns: false })).thread;
            const freshReason = ineligibilityReason(freshThread, cutoffSeconds, options.excludedThreadIds);
            const fileReason = rolloutWriteReason(freshThread, cutoffSeconds * MILLISECONDS_PER_SECOND);
            if (freshReason || fileReason) {
                recordSkip(freshReason || fileReason);
                continue;
            }
            const allDescendants = await listThreads(request, false, { ancestorThreadId: eachThread.id });
            if (allDescendants.length) {
                recordSkip('descendant');
                continue;
            }
            report.eligible += 1;
            allAttemptedArchiveIds.push(eachThread.id);
            await request('thread/archive', { threadId: eachThread.id });
            if (allAttemptedArchiveIds.length % 250 === 0) {
                process.stderr.write(`Sent ${allAttemptedArchiveIds.length} archive requests\n`);
            }
        } catch (error) {
            report.failed.push({ id: eachThread.id, error: String(error.message || error) });
        }
    }
    if (allAttemptedArchiveIds.length) {
        const archivedIds = new Set();
        try {
            for (const eachThread of await listThreads(request, true)) archivedIds.add(eachThread.id);
        } catch (error) {
            report.failed.push({ id: null, error: String(error.message || error) });
        }
        for (const eachThreadId of allAttemptedArchiveIds) {
            if (archivedIds.has(eachThreadId)) report.archived += 1;
            else {
                try {
                    const thread = (await request('thread/read', { threadId: eachThreadId, includeTurns: false })).thread;
                    if (isArchivedReadback(thread, eachThreadId, options.home)) report.archived += 1;
                    else report.failed.push({ id: eachThreadId, error: 'Archive readback missing' });
                } catch (error) {
                    report.failed.push({ id: eachThreadId, error: String(error.message || error) });
                }
            }
        }
    }
    return report;
}

async function main() {
    const options = parseOptions(process.argv.slice(2));
    const now = Date.now();
    let daemon;
    let report = createReport(options, Math.floor((now - options.inactiveDays * MILLISECONDS_PER_DAY) / MILLISECONDS_PER_SECOND));
    try {
        daemon = openDaemon(options);
        await daemon.initialize();
        report = await cleanseSessions(daemon.request, options, now, daemon.isHealthy);
    } catch (error) {
        report.failed.push({ id: null, error: String(error.message || error) });
    } finally {
        daemon?.close();
    }
    process.stdout.write(`${JSON.stringify(report)}\n`);
    if (report.failed.length) process.exitCode = 1;
}

if (process.argv[1] && existsSync(process.argv[1]) && isSameCanonicalPath(process.argv[1], scriptPath)) {
    main().catch(error => {
        process.stderr.write(`${error.message || error}\n`);
        process.exitCode = 1;
    });
}
