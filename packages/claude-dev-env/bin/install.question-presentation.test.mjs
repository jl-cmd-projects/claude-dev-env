import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const packageDirectory = fileURLToPath(new URL('..', import.meta.url));
const installerPath = join(packageDirectory, 'bin', 'install.mjs');
const policyPath = join(packageDirectory, 'rules', 'question-presentation.md');

function makeScratchHome(context) {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cde-question-'));
    context.after(() => rmSync(homeDirectory, { recursive: true, force: true }));
    return homeDirectory;
}

function installInScratchHome(homeDirectory, argumentsList = [], extraEnvironment = {}) {
    return spawnSync(process.execPath, [installerPath, ...argumentsList], {
        cwd: packageDirectory,
        encoding: 'utf8',
        env: {
            ...process.env,
            CLAUDE_CONFIG_DIR: undefined,
            LLM_SETTINGS_PROFILES_ROOT: undefined,
            CDE_INSTALL_PSTACK: '0',
            CDE_INSTALL_USAGE_WRAPUP: '0',
            HOME: homeDirectory,
            USERPROFILE: homeDirectory,
            CODEX_HOME: join(homeDirectory, '.codex'),
            GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
            ...extraEnvironment,
        },
    });
}

test('full install with pstack disabled delivers one question policy to Claude and Codex', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    const codexHooksPath = join(homeDirectory, '.codex', 'config.toml');
    const hooksConfiguration = '[features]\nhooks = false\n';
    mkdirSync(dirname(codexHooksPath), { recursive: true });
    writeFileSync(codexHooksPath, hooksConfiguration);

    const installation = installInScratchHome(homeDirectory, ['--no-pstack']);

    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const policyText = readFileSync(policyPath, 'utf8');
    assert.equal(readFileSync(join(homeDirectory, '.claude', 'rules', 'question-presentation.md'), 'utf8'), policyText);
    assert.match(readFileSync(codexGuidancePath, 'utf8'), /<!-- claude-dev-env question presentation: start -->/);
    assert.ok(readFileSync(codexGuidancePath, 'utf8').includes(policyText));
    assert.equal(readFileSync(codexHooksPath, 'utf8'), hooksConfiguration);
    const manifestPath = join(homeDirectory, '.claude', '.claude-dev-env-manifest.json');
    assert.equal(JSON.parse(readFileSync(manifestPath, 'utf8')).files.includes(codexGuidancePath), false);
});

test('full install preserves custom Codex notes and keeps the question block stable on repeat', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    mkdirSync(dirname(codexGuidancePath), { recursive: true });
    writeFileSync(codexGuidancePath, '# My notes\n\nKeep this line.\n');

    const firstInstallation = installInScratchHome(homeDirectory);
    assert.equal(firstInstallation.status, 0, firstInstallation.stdout + firstInstallation.stderr);
    const firstGuidance = readFileSync(codexGuidancePath, 'utf8');
    assert.ok(firstGuidance.startsWith('# My notes\n\nKeep this line.\n'));
    assert.ok(firstGuidance.includes(readFileSync(policyPath, 'utf8')));

    const secondInstallation = installInScratchHome(homeDirectory);
    assert.equal(secondInstallation.status, 0, secondInstallation.stdout + secondInstallation.stderr);
    assert.equal(readFileSync(codexGuidancePath, 'utf8'), firstGuidance);
});

test('uninstall removes question-only Codex guidance', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);

    const removal = installInScratchHome(homeDirectory, ['--uninstall']);

    assert.equal(removal.status, 0, removal.stdout + removal.stderr);
    assert.equal(existsSync(codexGuidancePath), false);
});

test('uninstall removes the managed blocks and preserves surrounding custom guidance', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    mkdirSync(dirname(codexGuidancePath), { recursive: true });
    const customGuidance = '# My notes\n\nKeep this line.\n';
    writeFileSync(codexGuidancePath, customGuidance);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    writeFileSync(codexGuidancePath, `${readFileSync(codexGuidancePath, 'utf8')}Trailing notes\n`);

    const removal = installInScratchHome(homeDirectory, ['--uninstall']);

    assert.equal(removal.status, 0, removal.stdout + removal.stderr);
    assert.equal(readFileSync(codexGuidancePath, 'utf8'), `${customGuidance}\n\nTrailing notes\n`);
});

for (const eachPriorGuidance of [null, '# Personal guidance\n']) {
    test(`an uninstall staging fault restores ${eachPriorGuidance ? 'custom' : 'question-only'} Codex guidance`, (context) => {
        const homeDirectory = makeScratchHome(context);
        const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
        if (eachPriorGuidance !== null) {
            mkdirSync(dirname(codexGuidancePath), { recursive: true });
            writeFileSync(codexGuidancePath, eachPriorGuidance);
        }
        const installation = installInScratchHome(homeDirectory);
        assert.equal(installation.status, 0, installation.stdout + installation.stderr);
        const installedGuidance = readFileSync(codexGuidancePath, 'utf8');

        const failedRemoval = installInScratchHome(homeDirectory, ['--uninstall'], {
            CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
        });

        assert.notEqual(failedRemoval.status, 0, failedRemoval.stdout + failedRemoval.stderr);
        assert.match(failedRemoval.stderr, /after_file_staging/);
        assert.equal(readFileSync(codexGuidancePath, 'utf8'), installedGuidance);
    });
}

test('full install leaves linked Codex guidance and its target unchanged', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    const userGuidancePath = join(homeDirectory, 'my-guidance.md');
    mkdirSync(dirname(codexGuidancePath), { recursive: true });
    writeFileSync(userGuidancePath, 'My linked notes\n');
    symlinkSync(userGuidancePath, codexGuidancePath);

    const installation = installInScratchHome(homeDirectory);

    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.equal(lstatSync(codexGuidancePath).isSymbolicLink(), true);
    assert.equal(readFileSync(userGuidancePath, 'utf8'), 'My linked notes\n');
});

test('full install with pstack disabled preserves an AGENTS.md directory and delivers Claude policy', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    mkdirSync(codexGuidancePath, { recursive: true });
    const notesPath = join(codexGuidancePath, 'notes.md');
    writeFileSync(notesPath, 'Directory notes\n');

    const installation = installInScratchHome(homeDirectory, ['--no-pstack']);

    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.equal(lstatSync(codexGuidancePath).isDirectory(), true);
    assert.equal(readFileSync(notesPath, 'utf8'), 'Directory notes\n');
    assert.equal(
        readFileSync(join(homeDirectory, '.claude', 'rules', 'question-presentation.md'), 'utf8'),
        readFileSync(policyPath, 'utf8'),
    );
});

test('a selected Claude profile receives the source rule and its Codex guidance', (context) => {
    const homeDirectory = makeScratchHome(context);
    const profileDirectory = join(homeDirectory, 'profile');

    const installation = installInScratchHome(homeDirectory, ['--target', profileDirectory]);

    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.equal(
        readFileSync(join(profileDirectory, 'rules', 'question-presentation.md'), 'utf8'),
        readFileSync(policyPath, 'utf8'),
    );
    assert.ok(readFileSync(join(profileDirectory, '.codex', 'AGENTS.md'), 'utf8').includes(readFileSync(policyPath, 'utf8')));
});

test('a successful pstack install retains its skill block and gains the question block', (context) => {
    const homeDirectory = makeScratchHome(context);
    const commandPath = join(homeDirectory, process.platform === 'win32' ? 'codex.cmd' : 'codex');
    writeFileSync(
        commandPath,
        process.platform === 'win32' ? '@echo off\r\nexit /b 0\r\n' : '#!/bin/sh\nexit 0\n',
        { mode: 0o755 },
    );

    const installation = installInScratchHome(homeDirectory, [], {
        CDE_INSTALL_PSTACK: '1',
        CDE_INSTALL_USAGE_WRAPUP: '0',
        CDE_CODEX_EXECUTABLE: commandPath,
        CDE_CLAUDE_EXECUTABLE: commandPath,
    });

    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const guidanceText = readFileSync(join(homeDirectory, '.codex', 'AGENTS.md'), 'utf8');
    assert.match(guidanceText, /<!-- claude-dev-env skill load: start -->/);
    assert.match(guidanceText, /<!-- claude-dev-env question presentation: start -->/);
    assert.ok(guidanceText.includes(readFileSync(policyPath, 'utf8')));
});

test('enabling pstack after a pstack-off install preserves question guidance', (context) => {
    const homeDirectory = makeScratchHome(context);
    const commandPath = join(homeDirectory, process.platform === 'win32' ? 'codex.cmd' : 'codex');
    writeFileSync(
        commandPath,
        process.platform === 'win32' ? '@echo off\r\nexit /b 0\r\n' : '#!/bin/sh\nexit 0\n',
        { mode: 0o755 },
    );
    const firstInstallation = installInScratchHome(homeDirectory);
    assert.equal(firstInstallation.status, 0, firstInstallation.stdout + firstInstallation.stderr);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    const firstGuidance = readFileSync(codexGuidancePath, 'utf8');

    const secondInstallation = installInScratchHome(homeDirectory, [], {
        CDE_INSTALL_PSTACK: '1',
        CDE_INSTALL_USAGE_WRAPUP: '0',
        CDE_CODEX_EXECUTABLE: commandPath,
        CDE_CLAUDE_EXECUTABLE: commandPath,
    });

    assert.equal(secondInstallation.status, 0, secondInstallation.stdout + secondInstallation.stderr);
    const updatedGuidance = readFileSync(codexGuidancePath, 'utf8');
    assert.ok(updatedGuidance.includes(firstGuidance));
    assert.match(updatedGuidance, /<!-- claude-dev-env skill load: start -->/);
    assert.match(updatedGuidance, /^feature, refactoring: gpt-6-sol$/m);
    assert.match(readFileSync(join(homeDirectory, '.codex', 'pstack-models.md'), 'utf8'), /^session hook: on$/m);
});

test('a failed pstack transition restores question-only guidance and removes its new model sheet', (context) => {
    const homeDirectory = makeScratchHome(context);
    const commandPath = join(homeDirectory, process.platform === 'win32' ? 'codex.cmd' : 'codex');
    writeFileSync(
        commandPath,
        process.platform === 'win32' ? '@echo off\r\nexit /b 0\r\n' : '#!/bin/sh\nexit 0\n',
        { mode: 0o755 },
    );
    const firstInstallation = installInScratchHome(homeDirectory);
    assert.equal(firstInstallation.status, 0, firstInstallation.stdout + firstInstallation.stderr);
    const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
    const priorGuidance = readFileSync(codexGuidancePath, 'utf8');

    const failedInstallation = installInScratchHome(homeDirectory, [], {
        CDE_INSTALL_PSTACK: '1',
        CDE_INSTALL_USAGE_WRAPUP: '0',
        CDE_CODEX_EXECUTABLE: commandPath,
        CDE_CLAUDE_EXECUTABLE: commandPath,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });

    assert.notEqual(failedInstallation.status, 0, failedInstallation.stdout + failedInstallation.stderr);
    assert.equal(readFileSync(codexGuidancePath, 'utf8'), priorGuidance);
    assert.equal(existsSync(join(homeDirectory, '.codex', 'pstack-models.md')), false);
});

for (const priorGuidance of [null, '# Personal guidance\n']) {
    test(`a staging fault restores ${priorGuidance ? 'existing' : 'missing'} Codex guidance`, (context) => {
        const homeDirectory = makeScratchHome(context);
        const codexGuidancePath = join(homeDirectory, '.codex', 'AGENTS.md');
        if (priorGuidance !== null) {
            mkdirSync(dirname(codexGuidancePath), { recursive: true });
            writeFileSync(codexGuidancePath, priorGuidance);
        }

        const installation = installInScratchHome(homeDirectory, [], {
            CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
        });

        assert.notEqual(installation.status, 0, installation.stdout + installation.stderr);
        assert.match(installation.stderr, /after_file_staging/);
        if (priorGuidance === null) {
            assert.equal(existsSync(codexGuidancePath), false);
        } else {
            assert.equal(readFileSync(codexGuidancePath, 'utf8'), priorGuidance);
        }
    });
}
