import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import {
    findFolderLockers,
    LOCKER_REASON_COMMAND_LINE,
    LOCKER_REASON_OPEN_FILE,
    lockedFolderAdvice,
    namesALockedFolder,
    parseLockerLines,
} from './folder-lockers.mjs';

test('a host error about a folder in use names a locked folder', () => {
    assert.equal(namesALockedFolder('could not be replaced: it is in use by another program (EPERM)'), true);
    assert.equal(namesALockedFolder('EBUSY: resource busy or locked'), true);
    assert.equal(namesALockedFolder('Failed to parse marketplace file'), false);
});

test('probe lines become one entry per process, and this process never counts', () => {
    const probeOutput = [
        '{"pid":19056,"name":"Cursor.exe","reason":"command-line"}',
        '{"pid":19056,"name":"Cursor.exe","reason":"open-file"}',
        'WARNING: noise',
        '{"pid":4242,"name":"pwsh.exe","reason":"open-file"}',
        '{"pid":7,"name":"node.exe","reason":"command-line"}',
    ].join('\r\n');
    assert.deepEqual(parseLockerLines(probeOutput, 7), [
        { pid: 19056, name: 'Cursor.exe', reason: LOCKER_REASON_COMMAND_LINE },
        { pid: 4242, name: 'pwsh.exe', reason: LOCKER_REASON_OPEN_FILE },
    ]);
});

test('only Windows runs the probe', () => {
    let probedFolder = null;
    const runProbe = folderPath => {
        probedFolder = folderPath;
        return '{"pid":5,"name":"Cursor.exe","reason":"command-line"}';
    };
    assert.deepEqual(findFolderLockers('/cache/pstack', { platform: 'linux', runProbe }), []);
    assert.equal(probedFolder, null);
    assert.equal(findFolderLockers('C:/cache/pstack', { platform: 'win32', runProbe }).length, 1);
    assert.equal(probedFolder, 'C:/cache/pstack');
});

test('the advice names each process to close, or says what else holds a folder', () => {
    assert.equal(
        lockedFolderAdvice('C:/cache/pstack', [{ pid: 19056, name: 'Cursor.exe', reason: LOCKER_REASON_COMMAND_LINE }]),
        'Close Cursor.exe (PID 19056, was started on a path inside it), which holds C:/cache/pstack, and run the install again.',
    );
    assert.match(lockedFolderAdvice('C:/cache/pstack', []), /working folder is inside it/);
});
