import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
    CODEX_CONFIG_FILE_NAME,
    codexSolSettingSnapshotPaths,
    removeCodexSolSetting,
    solSettingLines,
    writeCodexSolSetting,
} from './codex-trimmed-sol.mjs';

const packageDirectory = fileURLToPath(new URL('..', import.meta.url));
const installerPath = join(packageDirectory, 'bin', 'install.mjs');
const shippedPromptPath = join(packageDirectory, 'system-prompts', 'codex-sol.md');

function makeScratchHome(context) {
    const homeDirectory = mkdtempSync(join(tmpdir(), 'cde-sol-setting-'));
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

function settingText(instructionsPath, userText = '') {
    return [...solSettingLines(instructionsPath), userText].join('\n');
}

test('setting lines point model_instructions_file at the prompt and name no model', () => {
    const allLines = solSettingLines('/home/user/.claude/system-prompts/codex-sol.md');
    assert.ok(allLines.includes('model_instructions_file = "/home/user/.claude/system-prompts/codex-sol.md"'));
    assert.equal(allLines.some((eachLine) => /^\s*model\s*=/.test(eachLine)), false);
});

test('setting lines escape a Windows path as a TOML basic string', () => {
    assert.ok(solSettingLines('C:\\Users\\user\\.claude\\system-prompts\\codex-sol.md').includes(
        'model_instructions_file = "C:\\\\Users\\\\user\\\\.claude\\\\system-prompts\\\\codex-sol.md"',
    ));
});

test('writing twice changes the config once and keeps user settings below the line', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = 'model = "gpt-6.1-sol"\n\n[features]\nweb_search = true\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);
    assert.equal(writeCodexSolSetting(codexHome, '/prompt.md'), configPath);
    assert.equal(writeCodexSolSetting(codexHome, '/prompt.md'), null);
    assert.equal(readFileSync(configPath, 'utf8'), settingText('/prompt.md', userText));
    assert.equal(writeCodexSolSetting(codexHome, '/moved/prompt.md'), configPath);
    assert.equal(readFileSync(configPath, 'utf8'), settingText('/moved/prompt.md', userText));
    assert.deepEqual(codexSolSettingSnapshotPaths(codexHome), [configPath]);
    assert.equal(removeCodexSolSetting(codexHome), configPath);
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});

test('a config saved with CRLF line endings still has its package line rewritten and removed', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = 'model = "gpt-6.1-sol"\r\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, settingText('/prompt.md', userText).replace(/\n/g, '\r\n').replace(/\r\r/g, '\r'));
    assert.equal(writeCodexSolSetting(codexHome, '/moved/prompt.md'), configPath);
    assert.equal(readFileSync(configPath, 'utf8'), settingText('/moved/prompt.md', userText));
    writeFileSync(configPath, readFileSync(configPath, 'utf8').replace(/\r?\n/g, '\r\n'));
    assert.equal(removeCodexSolSetting(codexHome), configPath);
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});

test('a user-written top-level model_instructions_file is neither rewritten nor removed', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = 'model_instructions_file = "/mine.md"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);
    assert.equal(writeCodexSolSetting(codexHome, '/prompt.md'), null);
    assert.equal(removeCodexSolSetting(codexHome), null);
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});

test('a model_instructions_file inside a table does not block the top-level setting', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = '[profiles.other]\nmodel_instructions_file = "/other.md"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);
    assert.equal(writeCodexSolSetting(codexHome, '/prompt.md'), configPath);
    assert.equal(readFileSync(configPath, 'utf8'), settingText('/prompt.md', userText));
});

test('a directory at the config path is left alone', (context) => {
    const codexHome = join(makeScratchHome(context), '.codex');
    mkdirSync(join(codexHome, CODEX_CONFIG_FILE_NAME), { recursive: true });
    assert.equal(writeCodexSolSetting(codexHome, '/prompt.md'), null);
    assert.equal(removeCodexSolSetting(codexHome), null);
    assert.deepEqual(codexSolSettingSnapshotPaths(codexHome), []);
});

test('a missing config needs no prior snapshot', (context) => {
    assert.deepEqual(codexSolSettingSnapshotPaths(join(makeScratchHome(context), '.codex')), []);
});

test('full install points config.toml model_instructions_file at the installed trimmed prompt', (context) => {
    const homeDirectory = makeScratchHome(context);
    const configPath = join(homeDirectory, '.codex', CODEX_CONFIG_FILE_NAME);
    const installedPromptPath = join(homeDirectory, '.claude', 'system-prompts', 'codex-sol.md');

    const firstInstallation = installInScratchHome(homeDirectory);
    assert.equal(firstInstallation.status, 0, firstInstallation.stdout + firstInstallation.stderr);
    assert.equal(readFileSync(configPath, 'utf8'), settingText(installedPromptPath));
    assert.equal(readFileSync(installedPromptPath, 'utf8'), readFileSync(shippedPromptPath, 'utf8'));

    const secondInstallation = installInScratchHome(homeDirectory);
    assert.equal(secondInstallation.status, 0, secondInstallation.stdout + secondInstallation.stderr);
    assert.equal(secondInstallation.stdout.includes('Codex trimmed Sol prompt setting'), false);
    assert.equal(readFileSync(configPath, 'utf8'), settingText(installedPromptPath));
});

test('uninstall removes the package line and keeps the user config', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexHome = join(homeDirectory, '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = 'approval_policy = "never"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall']);
    assert.equal(uninstallation.status, 0, uninstallation.stdout + uninstallation.stderr);
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});

test('uninstall removes a config that held only the package line', (context) => {
    const homeDirectory = makeScratchHome(context);
    const configPath = join(homeDirectory, '.codex', CODEX_CONFIG_FILE_NAME);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall']);
    assert.equal(uninstallation.status, 0, uninstallation.stdout + uninstallation.stderr);
    assert.equal(existsSync(configPath), false);
});

test('failed uninstall restores the config with the package line', (context) => {
    const homeDirectory = makeScratchHome(context);
    const configPath = join(homeDirectory, '.codex', CODEX_CONFIG_FILE_NAME);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    const priorConfig = readFileSync(configPath, 'utf8');

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall'], {
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(uninstallation.status, 0);
    assert.match(uninstallation.stderr, /prior installation restored/);
    assert.equal(readFileSync(configPath, 'utf8'), priorConfig);
});

test('failed install restores a user config shared by two homes', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const userText = 'approval_policy = "never"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);

    const failedInstallation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(failedInstallation.status, 0);
    assert.match(failedInstallation.stderr, /prior installation restored/);
    assert.ok(failedInstallation.stdout.includes('Codex trimmed Sol prompt setting'));
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});

test('failed install removes a newly created config', (context) => {
    const homeDirectory = makeScratchHome(context);
    const installation = installInScratchHome(homeDirectory, [], {
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.ok(!existsSync(join(homeDirectory, '.codex', CODEX_CONFIG_FILE_NAME)));
});

test('failed install leaves a directory at the config path unchanged', (context) => {
    const firstHome = makeScratchHome(context);
    const secondHome = makeScratchHome(context);
    const codexHome = join(firstHome, '.codex');
    const sentinelPath = join(codexHome, CODEX_CONFIG_FILE_NAME, 'keep.txt');
    mkdirSync(join(codexHome, CODEX_CONFIG_FILE_NAME), { recursive: true });
    writeFileSync(sentinelPath, 'keep\n');
    const installation = installInScratchHome(secondHome, [], {
        CODEX_HOME: codexHome,
        CLAUDE_DEV_ENV_INSTALL_FAULT: 'after_file_staging',
    });
    assert.notEqual(installation.status, 0);
    assert.match(installation.stderr, /prior installation restored/);
    assert.equal(readFileSync(sentinelPath, 'utf8'), 'keep\n');
});
