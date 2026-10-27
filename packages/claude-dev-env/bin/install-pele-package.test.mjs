import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
    PELE_PACKAGE_NAME,
    PELE_PACKAGE_SPEC,
    installPelePackage,
    installedPeleVersion,
    peleInstallDirectory,
    removePelePackage,
} from './install-pele-package.mjs';
import { shouldInstallMarketplacePlugin } from './install-pstack-plugin.mjs';

function writeInstalledPele(installDirectory, version) {
    const packageDirectory = join(installDirectory, 'node_modules', PELE_PACKAGE_NAME);
    mkdirSync(packageDirectory, { recursive: true });
    writeFileSync(join(packageDirectory, 'package.json'), JSON.stringify({ name: PELE_PACKAGE_NAME, version }));
}

function fakeNpm({ latestVersion, installedAfterInstall, failOn }) {
    const recordedCalls = [];
    const recordedOptions = [];
    const run = (commandArguments, options) => {
        recordedCalls.push(commandArguments);
        recordedOptions.push(options);
        if (failOn === commandArguments[0]) return { status: 1, stdout: '', stderr: `${failOn} exploded` };
        if (commandArguments[0] === 'view') return { status: 0, stdout: `${latestVersion}\n`, stderr: '' };
        writeInstalledPele(options.cwd, installedAfterInstall ?? latestVersion);
        return { status: 0, stdout: '', stderr: '' };
    };
    return { run, recordedCalls, recordedOptions };
}

function withInstallDirectory(body) {
    const managedRoot = mkdtempSync(join(tmpdir(), 'cde-pele-'));
    try {
        body(peleInstallDirectory(managedRoot));
    } finally {
        rmSync(managedRoot, { recursive: true, force: true });
    }
}

test('the install directory sits under the managed root and the package is named pele', () => {
    assert.equal(PELE_PACKAGE_NAME, 'pele');
    assert.match(peleInstallDirectory('/home/dev/.claude').replaceAll('\\', '/'), /\/home\/dev\/\.claude\/tools\/pele$/);
});

test('the registry lookup runs beside the install folder, not in the caller directory', () => {
    const managedRoot = mkdtempSync(join(tmpdir(), 'cde-pele-'));
    try {
        const installDirectory = peleInstallDirectory(managedRoot);
        const { run, recordedOptions } = fakeNpm({ latestVersion: '1.2.0' });
        installPelePackage({ installDirectory, run });
        assert.equal(recordedOptions[0].cwd, managedRoot);
        assert.equal(recordedOptions[1].cwd, installDirectory);
    } finally {
        rmSync(managedRoot, { recursive: true, force: true });
    }
});

test('a timed out npm call names the limit and keeps the partial output', () => {
    withInstallDirectory(installDirectory => {
        const timedOut = () => ({
            status: null,
            stdout: '',
            stderr: 'npm warn config old setting',
            error: Object.assign(new Error('spawnSync npm ETIMEDOUT'), { code: 'ETIMEDOUT' }),
        });
        const outcome = installPelePackage({ installDirectory, run: timedOut });
        assert.equal(outcome.status, 'failed');
        assert.match(outcome.warning, /timed out after 120000 ms npm warn config old setting/);
    });
});

test('a missing install is installed at the latest registry version', () => {
    withInstallDirectory(installDirectory => {
        const { run, recordedCalls } = fakeNpm({ latestVersion: '1.2.0' });
        const outcome = installPelePackage({ installDirectory, run });
        assert.equal(outcome.status, 'installed');
        assert.equal(outcome.installedVersion, '1.2.0');
        assert.equal(installedPeleVersion(installDirectory), '1.2.0');
        assert.deepEqual(recordedCalls[1], ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--loglevel=error', 'pele@1.2.0']);
    });
});

test('an outdated install is updated and reports both versions', () => {
    withInstallDirectory(installDirectory => {
        writeInstalledPele(installDirectory, '1.0.0');
        const { run } = fakeNpm({ latestVersion: '1.2.0' });
        const outcome = installPelePackage({ installDirectory, run });
        assert.equal(outcome.status, 'updated');
        assert.equal(outcome.previousVersion, '1.0.0');
        assert.equal(outcome.installedVersion, '1.2.0');
    });
});

test('a current install runs no install command', () => {
    withInstallDirectory(installDirectory => {
        writeInstalledPele(installDirectory, '1.2.0');
        const { run, recordedCalls } = fakeNpm({ latestVersion: '1.2.0' });
        const outcome = installPelePackage({ installDirectory, run });
        assert.equal(outcome.status, 'current');
        assert.deepEqual(recordedCalls.map(eachCall => eachCall[0]), ['view']);
    });
});

test('a registry lookup failure keeps an existing install and fails a missing one', () => {
    withInstallDirectory(installDirectory => {
        const missing = installPelePackage({ installDirectory, run: fakeNpm({ failOn: 'view' }).run });
        assert.equal(missing.status, 'failed');
        assert.match(missing.warning, /view exploded/);
        writeInstalledPele(installDirectory, '1.0.0');
        const kept = installPelePackage({ installDirectory, run: fakeNpm({ failOn: 'view' }).run });
        assert.equal(kept.status, 'current');
        assert.equal(kept.installedVersion, '1.0.0');
        assert.match(kept.warning, /view exploded/);
    });
});

test('a registry answer that is not a plain version never reaches the install command', () => {
    for (const hostileAnswer of ['1.2.0 & echo pwned', '1.2.0\n&& calc', '^1.2.0', 'latest', '1.2', '1.2.0;rm']) {
        withInstallDirectory(installDirectory => {
            const { run, recordedCalls } = fakeNpm({ latestVersion: hostileAnswer });
            const outcome = installPelePackage({ installDirectory, run });
            assert.equal(outcome.status, 'failed', hostileAnswer);
            assert.match(outcome.warning, /not a version/);
            assert.deepEqual(recordedCalls.map(eachCall => eachCall[0]), ['view'], hostileAnswer);
            assert.equal(existsSync(join(installDirectory, 'package.json')), false);
        });
    }
});

test('a failing install command is reported and leaves the older version in place', () => {
    withInstallDirectory(installDirectory => {
        writeInstalledPele(installDirectory, '1.0.0');
        const outcome = installPelePackage({ installDirectory, run: fakeNpm({ latestVersion: '1.2.0', failOn: 'install' }).run });
        assert.equal(outcome.status, 'failed');
        assert.match(outcome.warning, /install exploded/);
        assert.equal(installedPeleVersion(installDirectory), '1.0.0');
    });
});

test('an install that does not land the requested version is reported as failed', () => {
    withInstallDirectory(installDirectory => {
        const outcome = installPelePackage({
            installDirectory,
            run: fakeNpm({ latestVersion: '1.2.0', installedAfterInstall: '0.9.0' }).run,
        });
        assert.equal(outcome.status, 'failed');
        assert.match(outcome.warning, /1\.2\.0/);
    });
});

test('a newer local copy is kept and never downgraded', () => {
    withInstallDirectory(installDirectory => {
        writeInstalledPele(installDirectory, '1.10.0');
        const { run, recordedCalls } = fakeNpm({ latestVersion: '1.9.3' });
        const outcome = installPelePackage({ installDirectory, run });
        assert.equal(outcome.status, 'current');
        assert.equal(outcome.installedVersion, '1.10.0');
        assert.deepEqual(recordedCalls.map(eachCall => eachCall[0]), ['view']);
    });
});

test('a missing npm skips the step and a fresh install writes its own host manifest', () => {
    withInstallDirectory(installDirectory => {
        const absentNpm = () => ({ status: null, stdout: '', stderr: '', error: Object.assign(new Error('spawn npm ENOENT'), { code: 'ENOENT' }) });
        const skipped = installPelePackage({ installDirectory, run: absentNpm });
        assert.equal(skipped.status, 'skipped');
        assert.equal(existsSync(join(installDirectory, 'package.json')), false);
        installPelePackage({ installDirectory, run: fakeNpm({ latestVersion: '1.2.0' }).run });
        const hostManifest = JSON.parse(readFileSync(join(installDirectory, 'package.json'), 'utf8'));
        assert.equal(hostManifest.private, true);
    });
});

test('removing the install folder deletes it once and reports an absent folder', () => {
    withInstallDirectory(installDirectory => {
        writeInstalledPele(installDirectory, '1.2.0');
        assert.equal(removePelePackage(installDirectory), true);
        assert.equal(existsSync(installDirectory), false);
        assert.equal(removePelePackage(installDirectory), false);
    });
});

test('a corrupt installed package.json reads as not installed', () => {
    withInstallDirectory(installDirectory => {
        const packageDirectory = join(installDirectory, 'node_modules', PELE_PACKAGE_NAME);
        mkdirSync(packageDirectory, { recursive: true });
        writeFileSync(join(packageDirectory, 'package.json'), '{not json');
        assert.equal(installedPeleVersion(installDirectory), null);
        assert.equal(existsSync(join(packageDirectory, 'package.json')), true);
        assert.equal(readFileSync(join(packageDirectory, 'package.json'), 'utf8'), '{not json');
    });
});

test('--no-pele and CDE_INSTALL_PELE=0 skip the step', () => {
    assert.equal(shouldInstallMarketplacePlugin(PELE_PACKAGE_SPEC, [], {}), true);
    assert.equal(shouldInstallMarketplacePlugin(PELE_PACKAGE_SPEC, ['--no-pele'], {}), false);
    assert.equal(shouldInstallMarketplacePlugin(PELE_PACKAGE_SPEC, [], { CDE_INSTALL_PELE: '0' }), false);
});

const INSTALLER_PATH = fileURLToPath(new URL('./install.mjs', import.meta.url));
const STUB_NPM_SOURCE = `#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
fs.appendFileSync(process.env.STUB_NPM_LOG, process.argv.slice(2).join(' ') + '\\n');
fs.appendFileSync(process.env.STUB_NPM_CWD_LOG, process.argv[2] + ' ' + process.cwd() + '\\n');
if (process.argv[2] === 'view') { process.stdout.write('3.4.5\\n'); process.exit(0); }
const packageDirectory = path.join(process.cwd(), 'node_modules', 'pele');
fs.mkdirSync(packageDirectory, { recursive: true });
fs.writeFileSync(path.join(packageDirectory, 'package.json'), JSON.stringify({ name: 'pele', version: '3.4.5' }));
`;

test('a full install adds Pele once, skips it on a rerun, and --uninstall removes it', { skip: process.platform === 'win32' }, () => {
    const scratchRoot = mkdtempSync(join(tmpdir(), 'cde-pele-full-'));
    try {
        const stubDirectory = join(scratchRoot, 'stub-bin');
        const homeDirectory = join(scratchRoot, 'home');
        const callLog = join(scratchRoot, 'npm-calls.log');
        const cwdLog = join(scratchRoot, 'npm-cwds.log');
        mkdirSync(stubDirectory, { recursive: true });
        mkdirSync(homeDirectory, { recursive: true });
        writeFileSync(join(stubDirectory, 'npm'), STUB_NPM_SOURCE);
        chmodSync(join(stubDirectory, 'npm'), 0o755);
        writeFileSync(join(homeDirectory, '.gitconfig'), '');
        const environment = {
            ...process.env,
            PATH: `${stubDirectory}:${process.env.PATH}`,
            STUB_NPM_LOG: callLog,
            STUB_NPM_CWD_LOG: cwdLog,
            LLM_SETTINGS_PROFILES_ROOT: undefined,
            HOME: homeDirectory,
            USERPROFILE: homeDirectory,
            CLAUDE_CONFIG_DIR: '',
            GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
            CDE_INSTALL_PSTACK: '0',
            CDE_INSTALL_DEEPSTACK: '0',
            CDE_INSTALL_USAGE_WRAPUP: '0',
            CDE_INSTALL_SUBAGENT_MODELS: '0',
            CDE_INSTALL_SECURITY_GUIDANCE: '0',
        };
        const peleDirectory = join(homeDirectory, '.claude', 'tools', 'pele');
        const firstRun = spawnSync(process.execPath, [INSTALLER_PATH], { encoding: 'utf8', env: environment });
        assert.equal(firstRun.status, 0, firstRun.stdout + firstRun.stderr);
        assert.match(firstRun.stdout, /Pele 3\.4\.5: installed/);
        assert.equal(installedPeleVersion(peleDirectory), '3.4.5');
        const secondRun = spawnSync(process.execPath, [INSTALLER_PATH], { encoding: 'utf8', env: environment });
        assert.equal(secondRun.status, 0, secondRun.stdout + secondRun.stderr);
        assert.match(secondRun.stdout, /Pele 3\.4\.5: current/);
        const installCalls = readFileSync(callLog, 'utf8').split('\n').filter(eachLine => eachLine.startsWith('install '));
        assert.equal(installCalls.length, 1);
        const viewCwd = readFileSync(cwdLog, 'utf8').split('\n').find(eachLine => eachLine.startsWith('view ')).slice('view '.length);
        assert.equal(viewCwd.startsWith(realpathSync(homeDirectory)), true, viewCwd);
        const optedOut = spawnSync(process.execPath, [INSTALLER_PATH, '--no-pele'], { encoding: 'utf8', env: environment });
        assert.equal(optedOut.status, 0, optedOut.stdout + optedOut.stderr);
        assert.doesNotMatch(optedOut.stdout, /Pele/);
        const uninstall = spawnSync(process.execPath, [INSTALLER_PATH, '--uninstall'], { encoding: 'utf8', env: environment });
        assert.equal(uninstall.status, 0, uninstall.stdout + uninstall.stderr);
        assert.equal(existsSync(peleDirectory), false);
    } finally {
        rmSync(scratchRoot, { recursive: true, force: true });
    }
});
