/**
 * Real-filesystem tests for Claude lookup pointers into the agents home.
 */

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import {
    existsSync,
    lstatSync,
    mkdirSync,
    mkdtempSync,
    readFileSync,
    realpathSync,
    rmSync,
    symlinkSync,
    writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    DIRECTORY_POINTER_TYPE_DIR,
    DIRECTORY_POINTER_TYPE_JUNCTION,
    POINTER_ACTION_ALREADY_POINTING,
    POINTER_ACTION_CREATED,
    directoryPointerTypeForPlatform,
    ensureDirectoryPointer,
    ensureLinkedSkillFolder,
    isDirectoryPointerTo,
    unlinkDirectoryPointerIfMatch,
} from './publish-directory-pointer.mjs';

function makeSandbox() {
    const root = mkdtempSync(join(tmpdir(), 'cdev-pointer-'));
    return {
        root,
        pointerPath: join(root, 'lookup', 'skills'),
        targetPath: join(root, 'canonical', 'skills'),
    };
}

function entryExistsWithoutFollowing(entryPath) {
    try {
        lstatSync(entryPath);
        return true;
    } catch {
        return false;
    }
}

test('directoryPointerTypeForPlatform uses a junction on Windows and a dir pointer elsewhere', () => {
    assert.equal(directoryPointerTypeForPlatform('win32'), DIRECTORY_POINTER_TYPE_JUNCTION);
    assert.equal(directoryPointerTypeForPlatform('linux'), DIRECTORY_POINTER_TYPE_DIR);
    assert.equal(directoryPointerTypeForPlatform('darwin'), DIRECTORY_POINTER_TYPE_DIR);
});

test('ensureDirectoryPointer writes a lookup pointer whose files are the canonical files', () => {
    const sandbox = makeSandbox();
    try {
        mkdirSync(sandbox.targetPath, { recursive: true });
        const canonicalFile = join(sandbox.targetPath, 'notes.md');
        writeFileSync(canonicalFile, 'canonical body\n');

        const publication = ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);
        assert.equal(publication.action, POINTER_ACTION_CREATED);
        assert.equal(lstatSync(sandbox.pointerPath).isSymbolicLink(), true);
        assert.equal(isDirectoryPointerTo(sandbox.pointerPath, sandbox.targetPath), true);
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'notes.md'), 'utf8'),
            'canonical body\n',
        );
        assert.equal(
            realpathSync(join(sandbox.pointerPath, 'notes.md')),
            realpathSync(canonicalFile),
        );
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureDirectoryPointer leaves a correct pointer in place', () => {
    const sandbox = makeSandbox();
    try {
        const firstPublication = ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);
        assert.equal(firstPublication.action, POINTER_ACTION_CREATED);
        const secondPublication = ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);
        assert.equal(secondPublication.action, POINTER_ACTION_ALREADY_POINTING);
        assert.equal(isDirectoryPointerTo(sandbox.pointerPath, sandbox.targetPath), true);
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureDirectoryPointer relocates a real lookup directory into the agents home', () => {
    const sandbox = makeSandbox();
    try {
        mkdirSync(sandbox.pointerPath, { recursive: true });
        writeFileSync(join(sandbox.pointerPath, 'personal.md'), 'user skill\n');
        mkdirSync(sandbox.targetPath, { recursive: true });
        writeFileSync(join(sandbox.targetPath, 'shipped.md'), 'package skill\n');

        ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);

        assert.equal(lstatSync(sandbox.pointerPath).isSymbolicLink(), true);
        assert.equal(
            readFileSync(join(sandbox.targetPath, 'personal.md'), 'utf8'),
            'user skill\n',
        );
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'personal.md'), 'utf8'),
            'user skill\n',
        );
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'shipped.md'), 'utf8'),
            'package skill\n',
        );
        assert.equal(existsSync(join(sandbox.targetPath, 'personal.md')), true);
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('unlinkDirectoryPointerIfMatch removes only a pointer that aims at the expected target', () => {
    const sandbox = makeSandbox();
    try {
        ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);
        writeFileSync(join(sandbox.targetPath, 'kept.md'), 'kept\n');
        assert.equal(
            unlinkDirectoryPointerIfMatch(sandbox.pointerPath, sandbox.targetPath),
            true,
        );
        assert.equal(existsSync(sandbox.pointerPath), false);
        assert.equal(readFileSync(join(sandbox.targetPath, 'kept.md'), 'utf8'), 'kept\n');
        assert.equal(
            unlinkDirectoryPointerIfMatch(sandbox.pointerPath, sandbox.targetPath),
            false,
        );
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder replaces a pointer with a folder that links each shipped skill', () => {
    const sandbox = makeSandbox();
    const pluginCacheSkill = join(sandbox.root, 'plugins', 'cache', 'plugin-skill');
    try {
        mkdirSync(join(sandbox.targetPath, 'shipped-skill'), { recursive: true });
        writeFileSync(join(sandbox.targetPath, 'shipped-skill', 'SKILL.md'), 'shipped body\n');
        mkdirSync(pluginCacheSkill, { recursive: true });
        symlinkSync(pluginCacheSkill, join(sandbox.targetPath, 'plugin-skill'), 'dir');
        ensureDirectoryPointer(sandbox.pointerPath, sandbox.targetPath);

        const { createdLinkPaths } = ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        assert.equal(lstatSync(sandbox.pointerPath).isDirectory(), true);
        assert.equal(lstatSync(sandbox.pointerPath).isSymbolicLink(), false);
        assert.equal(lstatSync(join(sandbox.pointerPath, 'shipped-skill')).isSymbolicLink(), true);
        assert.equal(
            isDirectoryPointerTo(
                join(sandbox.pointerPath, 'shipped-skill'),
                join(sandbox.targetPath, 'shipped-skill'),
            ),
            true,
        );
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'shipped-skill', 'SKILL.md'), 'utf8'),
            'shipped body\n',
        );
        assert.equal(entryExistsWithoutFollowing(join(sandbox.pointerPath, 'plugin-skill')), false);
        assert.deepEqual(createdLinkPaths, [join(sandbox.pointerPath, 'shipped-skill')]);
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder keeps a personal skill that exists only in the lookup folder', () => {
    const sandbox = makeSandbox();
    try {
        mkdirSync(join(sandbox.pointerPath, 'personal-skill'), { recursive: true });
        writeFileSync(join(sandbox.pointerPath, 'personal-skill', 'notes.md'), 'personal\n');
        mkdirSync(sandbox.targetPath, { recursive: true });

        const { createdLinkPaths } = ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        assert.equal(lstatSync(join(sandbox.pointerPath, 'personal-skill')).isDirectory(), true);
        assert.equal(lstatSync(join(sandbox.pointerPath, 'personal-skill')).isSymbolicLink(), false);
        assert.equal(existsSync(join(sandbox.targetPath, 'personal-skill')), false);
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'personal-skill', 'notes.md'), 'utf8'),
            'personal\n',
        );
        assert.deepEqual(createdLinkPaths, []);
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder removes a dangling link into the install folder and keeps a link to another folder', () => {
    const sandbox = makeSandbox();
    const otherSkill = join(sandbox.root, 'elsewhere', 'other-skill');
    try {
        mkdirSync(sandbox.targetPath, { recursive: true });
        mkdirSync(sandbox.pointerPath, { recursive: true });
        symlinkSync(join(sandbox.targetPath, 'retired-skill'), join(sandbox.pointerPath, 'retired-skill'), 'dir');
        mkdirSync(otherSkill, { recursive: true });
        symlinkSync(otherSkill, join(sandbox.pointerPath, 'other-skill'), 'dir');

        ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        assert.equal(entryExistsWithoutFollowing(join(sandbox.pointerPath, 'retired-skill')), false);
        assert.equal(lstatSync(join(sandbox.pointerPath, 'other-skill')).isSymbolicLink(), true);
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder creates no links on a second call and still reports the link in place', () => {
    const sandbox = makeSandbox();
    try {
        mkdirSync(join(sandbox.targetPath, 'shipped-skill'), { recursive: true });
        writeFileSync(join(sandbox.targetPath, 'shipped-skill', 'SKILL.md'), 'shipped body\n');
        ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        const secondCall = ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        assert.deepEqual(secondCall.createdLinkPaths, []);
        assert.deepEqual(secondCall.linkPaths, [join(sandbox.pointerPath, 'shipped-skill')]);
        assert.equal(
            isDirectoryPointerTo(
                join(sandbox.pointerPath, 'shipped-skill'),
                join(sandbox.targetPath, 'shipped-skill'),
            ),
            true,
        );
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder replaces a lookup link that aims at another directory and leaves that directory alone', () => {
    const sandbox = makeSandbox();
    const elsewhere = join(sandbox.root, 'elsewhere');
    try {
        mkdirSync(join(sandbox.targetPath, 'shipped-skill'), { recursive: true });
        writeFileSync(join(sandbox.targetPath, 'shipped-skill', 'SKILL.md'), 'shipped body\n');
        mkdirSync(elsewhere, { recursive: true });
        writeFileSync(join(elsewhere, 'notes.md'), 'elsewhere\n');
        mkdirSync(join(sandbox.root, 'lookup'), { recursive: true });
        symlinkSync(elsewhere, sandbox.pointerPath, 'dir');

        const { createdLinkPaths } = ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath);

        assert.equal(lstatSync(sandbox.pointerPath).isDirectory(), true);
        assert.equal(lstatSync(sandbox.pointerPath).isSymbolicLink(), false);
        assert.equal(isDirectoryPointerTo(join(sandbox.pointerPath, 'shipped-skill'), join(sandbox.targetPath, 'shipped-skill')), true);
        assert.deepEqual(createdLinkPaths, [join(sandbox.pointerPath, 'shipped-skill')]);
        assert.equal(readFileSync(join(elsewhere, 'notes.md'), 'utf8'), 'elsewhere\n');
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});

test('ensureLinkedSkillFolder moves a lookup file that conflicts with the agents home into the backup folder', () => {
    const sandbox = makeSandbox();
    const conflictBackup = join(sandbox.root, 'backup', 'skills');
    try {
        mkdirSync(join(sandbox.targetPath, 'shared-skill'), { recursive: true });
        writeFileSync(join(sandbox.targetPath, 'shared-skill', 'SKILL.md'), 'agents home body\n');
        mkdirSync(join(sandbox.pointerPath, 'shared-skill'), { recursive: true });
        writeFileSync(join(sandbox.pointerPath, 'shared-skill', 'SKILL.md'), 'local edit\n');
        writeFileSync(join(sandbox.pointerPath, 'shared-skill', 'extra.md'), 'lookup only\n');

        ensureLinkedSkillFolder(sandbox.pointerPath, sandbox.targetPath, conflictBackup);

        assert.equal(
            readFileSync(join(conflictBackup, 'shared-skill', 'SKILL.md'), 'utf8'),
            'local edit\n',
        );
        assert.equal(
            readFileSync(join(sandbox.targetPath, 'shared-skill', 'extra.md'), 'utf8'),
            'lookup only\n',
        );
        assert.equal(
            readFileSync(join(sandbox.pointerPath, 'shared-skill', 'SKILL.md'), 'utf8'),
            'agents home body\n',
        );
    } finally {
        rmSync(sandbox.root, { recursive: true, force: true });
    }
});
