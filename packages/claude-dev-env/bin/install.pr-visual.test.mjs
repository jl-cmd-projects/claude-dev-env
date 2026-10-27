import { strict as assert } from 'node:assert';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const PACKAGE_DIRECTORY = dirname(dirname(fileURLToPath(import.meta.url)));
const SKILL_PATH_SEGMENTS = ['.agents', 'skills', 'pr-visual'];
const REQUIRED_FILES = ['SKILL.md', 'scripts/collect.py', 'scripts/render.py', 'scripts/metrics.py', 'scripts/verify.py', 'scripts/visual_config/config/constants.py', 'assets/viewer.html', 'assets/icons.symbols', 'fixtures/bar.scene.json', 'fixtures/integrated.scene.json', 'references/formats.md'];
const INSTALL_MODES = [[], ['--only', 'core']];
const NPM_EXECUTABLE = process.platform === 'win32' ? 'npm.cmd' : 'npm';

test('packed full and core installs ship the runnable PR visual skill to the shared agents home', () => {
    const sandbox = mkdtempSync(join(tmpdir(), 'cde-pr-visual-'));
    try {
        const packed = JSON.parse(execFileSync(NPM_EXECUTABLE, ['pack', '--json', '--ignore-scripts', '--offline', '--cache', join(sandbox, 'npm-cache'), '--pack-destination', sandbox], { cwd: PACKAGE_DIRECTORY, encoding: 'utf8', shell: process.platform === 'win32' }));
        execFileSync('tar', ['-xzf', join(sandbox, packed[0].filename), '-C', sandbox]);
        const packaged = join(sandbox, 'package');
        for (const [eachIndex, eachArguments] of INSTALL_MODES.entries()) {
            const homeDirectory = join(sandbox, `home-${eachIndex}`);
            execFileSync(process.execPath, [join(packaged, 'bin/install.mjs'), ...eachArguments], {
                encoding: 'utf8',
                env: { ...process.env, CLAUDE_CONFIG_DIR: undefined, LLM_SETTINGS_PROFILES_ROOT: undefined, HOME: homeDirectory, USERPROFILE: homeDirectory, CODEX_HOME: join(homeDirectory, '.codex'), GIT_CONFIG_GLOBAL: join(homeDirectory, '.gitconfig'), CDE_INSTALL_PSTACK: '0', CDE_INSTALL_DEEPSTACK: '0', CDE_INSTALL_PELE: '0', CDE_INSTALL_USAGE_WRAPUP: '0', CDE_INSTALL_SUBAGENT_MODELS: '0', CDE_INSTALL_SECURITY_GUIDANCE: '0', CDE_INSTALL_DEEPEN_FIRST_PROMPT: '0' },
            });
            const installed = join(homeDirectory, ...SKILL_PATH_SEGMENTS);
            for (const eachFile of REQUIRED_FILES) assert.deepEqual(readFileSync(join(installed, eachFile)), readFileSync(join(packaged, ...SKILL_PATH_SEGMENTS, eachFile)));
            assert.equal(realpathSync(join(homeDirectory, '.claude/skills/pr-visual')), realpathSync(installed));
            const manifest = JSON.parse(readFileSync(join(homeDirectory, '.claude/.claude-dev-env-manifest.json'), 'utf8'));
            assert.ok(manifest.skills.includes('pr-visual'));
            const visual = join(sandbox, `visual-${eachIndex}.html`);
            execFileSync(process.platform === 'win32' ? 'python' : 'python3', [join(installed, 'scripts/render.py'), join(installed, 'fixtures/integrated.scene.json'), '--out', visual]);
            assert.ok(existsSync(visual));
            assert.match(readFileSync(visual, 'utf8'), /Duration \(ms\)/);
        }
    } finally {
        rmSync(sandbox, { recursive: true, force: true });
    }
});
