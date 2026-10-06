import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
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
            HOME: homeDirectory,
            USERPROFILE: homeDirectory,
            CODEX_HOME: join(homeDirectory, '.codex'),
            GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'),
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
});

test('a directory at the profile path is left alone', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    mkdirSync(join(codexHome, SOL_PROFILE_FILE_NAME), { recursive: true });
    assert.equal(writeCodexSolProfile(codexHome, '/prompt.md'), null);
    assert.equal(removeCodexSolProfile(codexHome), null);
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
