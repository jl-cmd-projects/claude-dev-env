import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import {
    chmodSync,
    lstatSync,
    mkdirSync,
    mkdtempSync,
    readFileSync,
    readdirSync,
    readlinkSync,
    rmSync,
    statSync,
    symlinkSync,
    utimesSync,
    writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { writeFileAtomically } from './write-file-atomically.mjs';

const FILE_SIZE_LIMIT_COMMAND = 'prlimit';
const isFileSizeLimitAvailable = spawnSync(FILE_SIZE_LIMIT_COMMAND, ['--version']).status === 0;
const isPosixPlatform = process.platform !== 'win32';
const PRIOR_SETTINGS_TEXT = '{\n    "prior": true\n}\n';
const NEW_SETTINGS_TEXT = `{\n    "next": "${'x'.repeat(4096)}"\n}\n`;


function withSandbox(runInSandbox) {
    const sandboxRoot = mkdtempSync(join(tmpdir(), 'cdev-atomic-write-'));
    try {
        runInSandbox(sandboxRoot);
    } finally {
        rmSync(sandboxRoot, { recursive: true, force: true });
    }
}


test('writeFileAtomically should replace an existing file with the complete new text and leave no temporary file', () => {
    withSandbox((sandboxRoot) => {
        const settingsPath = join(sandboxRoot, 'settings.json');
        writeFileSync(settingsPath, PRIOR_SETTINGS_TEXT);

        writeFileAtomically(settingsPath, NEW_SETTINGS_TEXT);

        assert.equal(readFileSync(settingsPath, 'utf8'), NEW_SETTINGS_TEXT);
        assert.deepEqual(readdirSync(sandboxRoot), ['settings.json']);
    });
});


test('writeFileAtomically should create a file that does not exist yet', () => {
    withSandbox((sandboxRoot) => {
        const settingsPath = join(sandboxRoot, 'settings.json');

        writeFileAtomically(settingsPath, NEW_SETTINGS_TEXT);

        assert.equal(readFileSync(settingsPath, 'utf8'), NEW_SETTINGS_TEXT);
        assert.deepEqual(readdirSync(sandboxRoot), ['settings.json']);
    });
});


test(
    'writeFileAtomically should keep the mode of the file it replaces',
    { skip: isPosixPlatform ? false : 'Windows keeps no POSIX mode bits' },
    () => {
        withSandbox((sandboxRoot) => {
            const settingsPath = join(sandboxRoot, 'settings.json');
            writeFileSync(settingsPath, PRIOR_SETTINGS_TEXT);
            chmodSync(settingsPath, 0o600);

            writeFileAtomically(settingsPath, NEW_SETTINGS_TEXT);

            assert.equal(statSync(settingsPath).mode & 0o777, 0o600);
        });
    },
);


test(
    'writeFileAtomically should write through a linked settings.json and keep the link',
    { skip: isPosixPlatform ? false : 'creating a file link on Windows needs a privilege the runner may lack' },
    () => {
        withSandbox((sandboxRoot) => {
            const sharedDirectory = join(sandboxRoot, 'shared');
            const profileDirectory = join(sandboxRoot, 'profile');
            mkdirSync(sharedDirectory);
            mkdirSync(profileDirectory);
            const sharedSettingsPath = join(sharedDirectory, 'settings.json');
            const linkedSettingsPath = join(profileDirectory, 'settings.json');
            writeFileSync(sharedSettingsPath, PRIOR_SETTINGS_TEXT);
            symlinkSync(sharedSettingsPath, linkedSettingsPath);

            writeFileAtomically(linkedSettingsPath, NEW_SETTINGS_TEXT);

            assert.equal(lstatSync(linkedSettingsPath).isSymbolicLink(), true, 'the profile entry is still a link');
            assert.equal(readlinkSync(linkedSettingsPath), sharedSettingsPath);
            assert.equal(readFileSync(sharedSettingsPath, 'utf8'), NEW_SETTINGS_TEXT);
            assert.deepEqual(readdirSync(sharedDirectory), ['settings.json']);
            assert.deepEqual(readdirSync(profileDirectory), ['settings.json']);
        });
    },
);


test(
    'writeFileAtomically should create the missing file at the end of a chain of links and keep every link',
    { skip: isPosixPlatform ? false : 'creating a file link on Windows needs a privilege the runner may lack' },
    () => {
        withSandbox((sandboxRoot) => {
            const profileDirectory = join(sandboxRoot, 'profile');
            const dotfilesDirectory = join(sandboxRoot, 'dotfiles');
            const storeDirectory = join(sandboxRoot, 'store');
            mkdirSync(profileDirectory);
            mkdirSync(dotfilesDirectory);
            mkdirSync(storeDirectory);
            const profileSettingsPath = join(profileDirectory, 'settings.json');
            const dotfilesSettingsPath = join(dotfilesDirectory, 'settings.json');
            const storedSettingsPath = join(storeDirectory, 'settings.json');
            symlinkSync(dotfilesSettingsPath, profileSettingsPath);
            symlinkSync(join('..', 'store', 'settings.json'), dotfilesSettingsPath);

            writeFileAtomically(profileSettingsPath, NEW_SETTINGS_TEXT);

            assert.equal(lstatSync(profileSettingsPath).isSymbolicLink(), true, 'the profile entry is still a link');
            assert.equal(lstatSync(dotfilesSettingsPath).isSymbolicLink(), true, 'the middle entry is still a link');
            assert.equal(readFileSync(storedSettingsPath, 'utf8'), NEW_SETTINGS_TEXT);
            assert.deepEqual(readdirSync(storeDirectory), ['settings.json']);
            assert.deepEqual(readdirSync(dotfilesDirectory), ['settings.json']);
        });
    },
);


test(
    'writeFileAtomically should refuse a link that loops back to itself and leave the link in place',
    { skip: isPosixPlatform ? false : 'creating a file link on Windows needs a privilege the runner may lack' },
    () => {
        withSandbox((sandboxRoot) => {
            const settingsPath = join(sandboxRoot, 'settings.json');
            symlinkSync('settings.json', settingsPath);

            assert.throws(() => writeFileAtomically(settingsPath, NEW_SETTINGS_TEXT), { code: 'ELOOP' });

            assert.equal(lstatSync(settingsPath).isSymbolicLink(), true, 'the looping entry is still a link');
            assert.deepEqual(readdirSync(sandboxRoot), ['settings.json']);
        });
    },
);


test(
    'writeFileAtomically should keep the prior file whole and remove its temporary file when the write fails part way',
    { skip: isFileSizeLimitAvailable ? false : `${FILE_SIZE_LIMIT_COMMAND} is not on PATH` },
    () => {
        withSandbox((sandboxRoot) => {
            const settingsPath = join(sandboxRoot, 'settings.json');
            writeFileSync(settingsPath, PRIOR_SETTINGS_TEXT);
            const writerScriptPath = join(sandboxRoot, 'write.mjs');
            writeFileSync(writerScriptPath, [
                `import { writeFileAtomically } from ${JSON.stringify(new URL('./write-file-atomically.mjs', import.meta.url).href)};`,
                `writeFileAtomically(${JSON.stringify(settingsPath)}, ${JSON.stringify(NEW_SETTINGS_TEXT)});`,
            ].join('\n'));

            const limitedRun = spawnSync(
                FILE_SIZE_LIMIT_COMMAND,
                [`--fsize=${Math.floor(NEW_SETTINGS_TEXT.length / 2)}`, process.execPath, writerScriptPath],
                { encoding: 'utf8' },
            );

            assert.notEqual(limitedRun.status, 0, 'the write past the file size limit fails');
            assert.match(limitedRun.stderr, /EFBIG/);
            assert.equal(readFileSync(settingsPath, 'utf8'), PRIOR_SETTINGS_TEXT);
            assert.deepEqual(readdirSync(sandboxRoot).sort(), ['settings.json', 'write.mjs']);
        });
    },
);


const KILL_AT_TARGET_CHANGE_PRELOAD = `
const fs = require('node:fs');
const targetPath = process.env.KILL_TARGET_PATH;
const originalWriteFileSync = fs.writeFileSync;
const originalRenameSync = fs.renameSync;
fs.writeFileSync = function (filePath, data, options) {
    if (String(filePath) === targetPath) {
        const text = String(data);
        originalWriteFileSync(filePath, text.slice(0, Math.floor(text.length / 2)));
        process.kill(process.pid, 'SIGKILL');
    }
    return originalWriteFileSync.apply(this, arguments);
};
fs.renameSync = function (sourcePath, destinationPath) {
    if (String(destinationPath) === targetPath) {
        process.kill(process.pid, 'SIGKILL');
    }
    return originalRenameSync.apply(this, arguments);
};
require('node:module').syncBuiltinESMExports();
`;


test(
    'writeFileAtomically should keep the prior file whole when the writer is killed as the target changes',
    { skip: isPosixPlatform ? false : 'a SIGKILL a process sends itself is POSIX only' },
    () => {
        withSandbox((sandboxRoot) => {
            const settingsPath = join(sandboxRoot, 'settings.json');
            writeFileSync(settingsPath, PRIOR_SETTINGS_TEXT);
            const preloadPath = join(sandboxRoot, 'kill-at-target-change.cjs');
            writeFileSync(preloadPath, KILL_AT_TARGET_CHANGE_PRELOAD);
            const writerScriptPath = join(sandboxRoot, 'write.mjs');
            writeFileSync(writerScriptPath, [
                `import { writeFileAtomically } from ${JSON.stringify(new URL('./write-file-atomically.mjs', import.meta.url).href)};`,
                `writeFileAtomically(${JSON.stringify(settingsPath)}, ${JSON.stringify(NEW_SETTINGS_TEXT)});`,
            ].join('\n'));

            const killedRun = spawnSync(
                process.execPath,
                ['--require', preloadPath, writerScriptPath],
                { encoding: 'utf8', env: { ...process.env, KILL_TARGET_PATH: settingsPath } },
            );

            assert.equal(killedRun.signal, 'SIGKILL', killedRun.stderr);
            assert.equal(readFileSync(settingsPath, 'utf8'), PRIOR_SETTINGS_TEXT);
        });
    },
);


function exitedProcessId() {
    return spawnSync(process.execPath, ['-e', '']).pid;
}


test('writeFileAtomically should remove old temporary files of this target whose writer is gone', () => {
    withSandbox((sandboxRoot) => {
        const settingsPath = join(sandboxRoot, 'settings.json');
        writeFileSync(settingsPath, PRIOR_SETTINGS_TEXT);
        const goneWriterId = exitedProcessId();
        const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
        const staleName = `.settings.json.${goneWriterId}.aaaaaaaaaaaa.tmp`;
        const liveWriterName = `.settings.json.${process.pid}.bbbbbbbbbbbb.tmp`;
        const freshName = `.settings.json.${goneWriterId}.cccccccccccc.tmp`;
        const otherTargetName = `.other.json.${goneWriterId}.dddddddddddd.tmp`;
        for (const eachName of [staleName, liveWriterName, freshName, otherTargetName]) {
            writeFileSync(join(sandboxRoot, eachName), '{"half":');
        }
        for (const eachName of [staleName, liveWriterName, otherTargetName]) {
            utimesSync(join(sandboxRoot, eachName), hourAgo, hourAgo);
        }

        writeFileAtomically(settingsPath, NEW_SETTINGS_TEXT);

        assert.equal(readFileSync(settingsPath, 'utf8'), NEW_SETTINGS_TEXT);
        assert.deepEqual(
            readdirSync(sandboxRoot).sort(),
            [freshName, otherTargetName, liveWriterName, 'settings.json'].sort(),
        );
    });
});
