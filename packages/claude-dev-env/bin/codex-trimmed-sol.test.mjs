import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
    codexSolProfileSnapshotPaths,
    removeCodexSolProfile,
    SOL_PROFILE_FILE_NAME,
    solProfileContent,
    writeCodexSolProfile,
} from './codex-trimmed-sol.mjs';

const packageDirectory = fileURLToPath(new URL('..', import.meta.url));
const installerPath = join(packageDirectory, 'bin', 'install.mjs');
const shippedPromptPath = join(packageDirectory, 'system-prompts', 'codex-sol.md');

function makeScratchHome(context) {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cde-sol-profile-'));
    context.after(() => rmSync(homeDirectory, { recursive: true, force: true }));
    return homeDirectory;
}

function installInScratchHome(homeDirectory, argumentsList = [], environment = {}) {
    return spawnSync(process.execPath, [installerPath, ...argumentsList], {
        cwd: packageDirectory,
        encoding: 'utf8',
        env: {
            ...process.env,
            CLAUDE_CONFIG_DIR: undefined,
            LLM_SETTINGS_PROFILES_ROOT: undefined,
            CDE_INSTALL_PSTACK: '0',
            CDE_INSTALL_USAGE_WRAPUP: '0',
            CDE_INSTALL_SUBAGENT_MODELS: '0',
            CLAUDE_DEV_ENV_INSTALL_FAULT: undefined,
            HOME: homeDirectory,
            USERPROFILE: homeDirectory,
            CODEX_HOME: join(homeDirectory, '.codex'),
            GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
            TEMP: homeDirectory,
            TMP: homeDirectory,
            ...environment,
        },
    });
}

test('profile text runs gpt-6.1-sol on the named prompt file', () => {
    const profileText = solProfileContent('/home/user/.claude/system-prompts/codex-sol.md');
    const allLines = profileText.split('\n');
    assert.ok(allLines.includes('model = "gpt-6.1-sol"'));
    assert.ok(allLines.includes('model_instructions_file = "/home/user/.claude/system-prompts/codex-sol.md"'));
});

test('profile text escapes a Windows path as a TOML basic string', () => {
    const profileText = solProfileContent('C:\\Users\\user\\.claude\\system-prompts\\codex-sol.md');
    assert.ok(profileText.split('\n').includes(
        'model_instructions_file = "C:\\\\Users\\\\user\\\\.claude\\\\system-prompts\\\\codex-sol.md"',
    ));
});

test('writing twice changes the file once', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    assert.equal(writeCodexSolProfile(codexHome, '/prompt.md'), profilePath);
    assert.equal(writeCodexSolProfile(codexHome, '/prompt.md'), null);
    assert.equal(readFileSync(profilePath, 'utf8'), solProfileContent('/prompt.md'));
    assert.equal(writeCodexSolProfile(codexHome, '/moved/prompt.md'), profilePath);
    assert.equal(readFileSync(profilePath, 'utf8'), solProfileContent('/moved/prompt.md'));
    assert.deepEqual(codexSolProfileSnapshotPaths(codexHome), [profilePath]);
});

test('a user-owned profile file is neither rewritten nor removed', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const userText = 'model = "gpt-6-sol"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(profilePath, userText);
    assert.equal(writeCodexSolProfile(codexHome, '/prompt.md'), null);
    assert.equal(removeCodexSolProfile(codexHome), null);
    assert.equal(readFileSync(profilePath, 'utf8'), userText);
    assert.deepEqual(codexSolProfileSnapshotPaths(codexHome), []);
});

test('a directory at the profile path is left alone', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    mkdirSync(join(codexHome, SOL_PROFILE_FILE_NAME), { recursive: true });
    assert.equal(writeCodexSolProfile(codexHome, '/prompt.md'), null);
    assert.equal(removeCodexSolProfile(codexHome), null);
    assert.deepEqual(codexSolProfileSnapshotPaths(codexHome), []);
});

test('a missing Sol profile needs no prior snapshot', (context) => {
    assert.deepEqual(codexSolProfileSnapshotPaths(join(makeScratchHome(context), '.codex')), []);
});

test('full install points the Codex Sol profile at the installed trimmed prompt', (context) => {
    const homeDirectory = makeScratchHome(context);
    const profilePath = join(homeDirectory, '.codex', SOL_PROFILE_FILE_NAME);
    const installedPromptPath = join(homeDirectory, '.claude', 'system-prompts', 'codex-sol.md');

    const firstInstallation = installInScratchHome(homeDirectory);
    assert.equal(firstInstallation.status, 0, firstInstallation.stdout + firstInstallation.stderr);
    assert.equal(readFileSync(profilePath, 'utf8'), solProfileContent(installedPromptPath));
    assert.equal(readFileSync(installedPromptPath, 'utf8'), readFileSync(shippedPromptPath, 'utf8'));

    const secondInstallation = installInScratchHome(homeDirectory);
    assert.equal(secondInstallation.status, 0, secondInstallation.stdout + secondInstallation.stderr);
    assert.equal(secondInstallation.stdout.includes('Codex trimmed Sol profile'), false);
    assert.equal(readFileSync(profilePath, 'utf8'), solProfileContent(installedPromptPath));
});

test('uninstall removes the package Sol profile', (context) => {
    const homeDirectory = makeScratchHome(context);
    const profilePath = join(homeDirectory, '.codex', SOL_PROFILE_FILE_NAME);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.ok(existsSync(profilePath));

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall']);
    assert.equal(uninstallation.status, 0, uninstallation.stdout + uninstallation.stderr);
    assert.equal(existsSync(profilePath), false);
});

test('failed uninstall restores the package Sol profile', (context) => {
    const homeDirectory = makeScratchHome(context);
    const profilePath = join(homeDirectory, '.codex', SOL_PROFILE_FILE_NAME);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const priorProfile = readFileSync(profilePath, 'utf8');

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall'], {
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(uninstallation.status, 0);
    assert.match(uninstallation.stderr, /prior installation restored/);
    assert.equal(readFileSync(profilePath, 'utf8'), priorProfile);
});

test('failed install restores a package Sol profile shared by two homes', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const promptPath = join(firstHome, '.claude', 'system-prompts', 'codex-sol.md');
    const installation = installInScratchHome(firstHome);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const priorProfile = readFileSync(profilePath);
    const priorPrompt = readFileSync(promptPath);

    const failedInstallation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(failedInstallation.status, 0);
    assert.match(failedInstallation.stderr, /prior installation restored/);
    assert.ok(failedInstallation.stdout.includes('Codex trimmed Sol profile'));
    assert.deepEqual(readFileSync(profilePath), priorProfile);
    assert.deepEqual(readFileSync(promptPath), priorPrompt);
    assert.ok(!existsSync(join(secondHome, '.claude', 'system-prompts', 'codex-sol.md')));
});

test('failed install removes a newly created package Sol profile', (context) => {
    const homeDirectory = makeScratchHome(context);
    const installation = installInScratchHome(homeDirectory, [], {
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.ok(!existsSync(join(homeDirectory, '.codex', SOL_PROFILE_FILE_NAME)));
});

test('failed install leaves a user-owned shared Sol profile unchanged', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const userProfile = 'model = "gpt-6-sol"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(profilePath, userProfile);
    const installation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.equal(readFileSync(profilePath, 'utf8'), userProfile);
});

test('failed install leaves a directory at the shared Sol profile path unchanged', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const sentinelPath = join(profilePath, 'keep.txt');
    mkdirSync(profilePath, { recursive: true });
    writeFileSync(sentinelPath, 'keep\n');
    const installation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.equal(readFileSync(sentinelPath, 'utf8'), 'keep\n');
});

test('failed install leaves a junction at the shared Sol profile path unchanged', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const profilePath = join(codexHome, SOL_PROFILE_FILE_NAME);
    const destination = join(firstHome, 'profile-directory');
    const sentinelPath = join(destination, 'keep.txt');
    mkdirSync(codexHome, { recursive: true });
    mkdirSync(destination);
    writeFileSync(sentinelPath, 'keep\n');
    symlinkSync(destination, profilePath, 'junction');
    const installation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.ok(lstatSync(profilePath).isSymbolicLink());
    assert.equal(readFileSync(sentinelPath, 'utf8'), 'keep\n');
});
