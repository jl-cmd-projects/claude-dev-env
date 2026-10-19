import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
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
            CDE_INSTALL_DEEPSTACK: '0',
            CDE_INSTALL_USAGE_WRAPUP: '0',
            CDE_INSTALL_SUBAGENT_MODELS: '0',
            CDE_INSTALL_DEEPEN_FIRST_PROMPT: '0',
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
    const installedPromptPath = join(homeDirectory, '.codex', 'codex-sol.md');

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

test('the prompt the setting names survives a prune of the managed Claude files', (context) => {
    const homeDirectory = makeScratchHome(context);
    const configPath = join(homeDirectory, '.codex', CODEX_CONFIG_FILE_NAME);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    rmSync(join(homeDirectory, '.claude', 'system-prompts'), { recursive: true, force: true });
    const namedPath = JSON.parse(readFileSync(configPath, 'utf8').split('\n')[1].split(' = ')[1]);
    assert.equal(existsSync(namedPath), true);
});

test('uninstall removes the Codex copy of the prompt', (context) => {
    const homeDirectory = makeScratchHome(context);
    const promptPath = join(homeDirectory, '.codex', 'codex-sol.md');
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.equal(existsSync(promptPath), true);
    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall']);
    assert.equal(uninstallation.status, 0, uninstallation.stdout + uninstallation.stderr);
    assert.equal(existsSync(promptPath), false);
});

test('uninstall removes the Codex copy of the prompt when the user wrote their own setting', (context) => {
    const homeDirectory = makeScratchHome(context);
    const codexHome = join(homeDirectory, '.codex');
    const configPath = join(codexHome, CODEX_CONFIG_FILE_NAME);
    const promptPath = join(codexHome, 'codex-sol.md');
    const userText = 'model_instructions_file = "/mine.md"\n';
    mkdirSync(codexHome, { recursive: true });
    writeFileSync(configPath, userText);
    const installation = installInScratchHome(homeDirectory);
    assert.equal(installation.status, 0, installation.stdout + installation.stderr);
    assert.equal(existsSync(promptPath), true);
    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall']);
    assert.equal(uninstallation.status, 0, uninstallation.stdout + uninstallation.stderr);
    assert.equal(existsSync(promptPath), false);
    assert.equal(readFileSync(configPath, 'utf8'), userText);
});


function makeLinkedCodexHomes(context) {
    const homeDirectory = makeScratchHome(context);
    const ownerHome = join(homeDirectory, '.codex');
    const linkedHome = join(homeDirectory, '.codex-editor');
    mkdirSync(ownerHome, { recursive: true });
    mkdirSync(linkedHome, { recursive: true });
    writeFileSync(join(ownerHome, CODEX_CONFIG_FILE_NAME), 'approval_policy = "never"\n');
    try {
        symlinkSync(join(ownerHome, CODEX_CONFIG_FILE_NAME), join(linkedHome, CODEX_CONFIG_FILE_NAME), 'file');
    } catch (error) {
        if (error.code === 'EPERM') return null;
        throw error;
    }
    return { homeDirectory, ownerHome, linkedHome };
}

test('a home whose config.toml links to another home names the prompt beside the real file', (context) => {
    const homes = makeLinkedCodexHomes(context);
    if (!homes) return context.skip('this account cannot create symlinks');
    const { homeDirectory, ownerHome, linkedHome } = homes;
    writeFileSync(join(linkedHome, 'codex-sol.md'), 'left by an earlier install\n');

    assert.equal(installInScratchHome(homeDirectory, [], { CODEX_HOME: ownerHome }).status, 0);
    const linkedInstallation = installInScratchHome(homeDirectory, [], { CODEX_HOME: linkedHome });

    assert.equal(linkedInstallation.status, 0, linkedInstallation.stderr);
    const configText = readFileSync(join(ownerHome, CODEX_CONFIG_FILE_NAME), 'utf8');
    assert.ok(configText.includes(`model_instructions_file = ${JSON.stringify(join(ownerHome, 'codex-sol.md'))}`), configText);
    assert.equal(readFileSync(join(ownerHome, 'codex-sol.md'), 'utf8'), readFileSync(shippedPromptPath, 'utf8'));
    assert.equal(existsSync(join(linkedHome, 'codex-sol.md')), false);
});

test('uninstall from a home whose config.toml is linked keeps the shared setting and prompt', (context) => {
    const homes = makeLinkedCodexHomes(context);
    if (!homes) return context.skip('this account cannot create symlinks');
    const { homeDirectory, ownerHome, linkedHome } = homes;
    assert.equal(installInScratchHome(homeDirectory, [], { CODEX_HOME: ownerHome }).status, 0);
    assert.equal(installInScratchHome(homeDirectory, [], { CODEX_HOME: linkedHome }).status, 0);

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall'], { CODEX_HOME: linkedHome });

    assert.equal(uninstallation.status, 0, uninstallation.stderr);
    const configText = readFileSync(join(ownerHome, CODEX_CONFIG_FILE_NAME), 'utf8');
    assert.ok(configText.includes(`model_instructions_file = ${JSON.stringify(join(ownerHome, 'codex-sol.md'))}`), configText);
    assert.equal(existsSync(join(ownerHome, 'codex-sol.md')), true);
});

test('a home whose config.toml is a hard link to the main home\'s file names the prompt in the main home', (context) => {
    const homeDirectory = makeScratchHome(context);
    const mainHome = join(homeDirectory, '.codex');
    const linkedHome = join(homeDirectory, '.codex-editor');
    mkdirSync(mainHome, { recursive: true });
    mkdirSync(linkedHome, { recursive: true });
    writeFileSync(join(mainHome, CODEX_CONFIG_FILE_NAME), 'approval_policy = "never"\n');
    linkSync(join(mainHome, CODEX_CONFIG_FILE_NAME), join(linkedHome, CODEX_CONFIG_FILE_NAME));
    assert.equal(installInScratchHome(homeDirectory, [], { CODEX_HOME: mainHome }).status, 0);

    const linkedInstallation = installInScratchHome(homeDirectory, [], { CODEX_HOME: linkedHome });
    assert.equal(linkedInstallation.status, 0, linkedInstallation.stderr);
    const sharedLine = `model_instructions_file = ${JSON.stringify(join(mainHome, 'codex-sol.md'))}`;
    assert.ok(readFileSync(join(mainHome, CODEX_CONFIG_FILE_NAME), 'utf8').includes(sharedLine));
    assert.equal(existsSync(join(linkedHome, 'codex-sol.md')), false);

    const uninstallation = installInScratchHome(homeDirectory, ['--uninstall'], { CODEX_HOME: linkedHome });
    assert.equal(uninstallation.status, 0, uninstallation.stderr);
    assert.ok(readFileSync(join(mainHome, CODEX_CONFIG_FILE_NAME), 'utf8').includes(sharedLine));
    assert.equal(existsSync(join(mainHome, 'codex-sol.md')), true);
});

test('a main home whose config.toml links into a dotfiles folder keeps the prompt in CODEX_HOME, and uninstall removes the line', (context) => {
    const homeDirectory = makeScratchHome(context);
    const mainHome = join(homeDirectory, '.codex');
    const dotfilesDirectory = join(homeDirectory, 'dotfiles', 'codex');
    mkdirSync(mainHome, { recursive: true });
    mkdirSync(dotfilesDirectory, { recursive: true });
    writeFileSync(join(dotfilesDirectory, CODEX_CONFIG_FILE_NAME), 'approval_policy = "never"\n');
    try {
        symlinkSync(join(dotfilesDirectory, CODEX_CONFIG_FILE_NAME), join(mainHome, CODEX_CONFIG_FILE_NAME), 'file');
    } catch (error) {
        if (error.code === 'EPERM') return context.skip('this account cannot create symlinks');
        throw error;
    }

    assert.equal(installInScratchHome(homeDirectory, [], { CODEX_HOME: mainHome }).status, 0);
    assert.ok(readFileSync(join(dotfilesDirectory, CODEX_CONFIG_FILE_NAME), 'utf8')
        .includes(`model_instructions_file = ${JSON.stringify(join(mainHome, 'codex-sol.md'))}`));
    assert.equal(existsSync(join(dotfilesDirectory, 'codex-sol.md')), false);

    assert.equal(installInScratchHome(homeDirectory, ['--uninstall'], { CODEX_HOME: mainHome }).status, 0);
    assert.equal(readFileSync(join(dotfilesDirectory, CODEX_CONFIG_FILE_NAME), 'utf8'), 'approval_policy = "never"\n');
    assert.equal(existsSync(join(mainHome, 'codex-sol.md')), false);
});
