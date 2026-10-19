import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
    INSTALL_ENTRY,
    PACKAGE_ROOT,
    SANDBOX_GIT_CONFIG_BODY,
    SANDBOX_GIT_CONFIG_NAME,
    createScratchHome,
    removeScratchHome,
    runInstaller,
    scratchHomeEnvironment,
} from './scratch-home-install.mjs';

test('the package root and install entry resolve to files that exist', () => {
    assert.equal(existsSync(INSTALL_ENTRY), true, INSTALL_ENTRY);
    assert.equal(existsSync(join(PACKAGE_ROOT, 'package.json')), true, PACKAGE_ROOT);
});

test('a scratch home starts with an isolated global git configuration and is removable', () => {
    const scratchHome = createScratchHome();
    try {
        const gitConfigPath = join(scratchHome, SANDBOX_GIT_CONFIG_NAME);
        assert.equal(readFileSync(gitConfigPath, 'utf8'), SANDBOX_GIT_CONFIG_BODY);
        assert.equal(existsSync(join(scratchHome, '.claude')), false);

        const environment = scratchHomeEnvironment(scratchHome);
        assert.equal(environment.HOME, scratchHome);
        assert.equal(environment.USERPROFILE, scratchHome);
        assert.equal(environment.GIT_CONFIG_GLOBAL, gitConfigPath);
        assert.equal(environment.CODEX_HOME, join(scratchHome, '.codex'));
    } finally {
        removeScratchHome(scratchHome);
    }
    assert.equal(existsSync(scratchHome), false);
});

test('the installer runs against a scratch home and leaves the caller home alone', () => {
    const scratchHome = createScratchHome();
    try {
        const help = runInstaller(scratchHome, ['--help']);
        assert.equal(help.status, 0, `${help.stdout}\n${help.stderr}`);
        assert.match(help.stdout, /Usage:/);
        assert.equal(existsSync(join(scratchHome, '.claude')), false);
    } finally {
        removeScratchHome(scratchHome);
    }
});

test('an install into a scratch home leaves the caller Codex home config alone', () => {
    const callerCodexHome = mkdtempSync(join(tmpdir(), 'cde-caller-codex-'));
    const callerConfigPath = join(callerCodexHome, 'config.toml');
    const callerConfigBody = 'model = "caller"\n';
    writeFileSync(callerConfigPath, callerConfigBody);
    const priorCodexHome = process.env.CODEX_HOME;
    process.env.CODEX_HOME = callerCodexHome;
    const scratchHome = createScratchHome();
    try {
        const install = runInstaller(scratchHome, []);
        assert.equal(install.status, 0, `${install.stdout}\n${install.stderr}`);
        assert.equal(readFileSync(callerConfigPath, 'utf8'), callerConfigBody);
    } finally {
        if (priorCodexHome === undefined) delete process.env.CODEX_HOME;
        else process.env.CODEX_HOME = priorCodexHome;
        removeScratchHome(scratchHome);
        rmSync(callerCodexHome, { recursive: true, force: true });
    }
});
