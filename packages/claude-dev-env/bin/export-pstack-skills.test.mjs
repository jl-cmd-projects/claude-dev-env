import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { exportPstackSkills } from './export-pstack-skills.mjs';

function fixture(context) {
    const root = mkdtempSync(join(tmpdir(), 'pstack-export-test-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const plugin = join(root, 'plugin');
    const target = join(root, 'repo', '.agents', 'skills');
    mkdirSync(join(plugin, '.codex-plugin'), { recursive: true });
    writeFileSync(join(plugin, '.codex-plugin', 'plugin.json'), JSON.stringify({
        name: 'pstack', version: '0.9.53', repository: 'https://github.com/michael-denyer/pstack-claude', skills: './skills/',
    }));
    mkdirSync(join(plugin, 'skills', 'poteto-mode', 'references'), { recursive: true });
    mkdirSync(join(plugin, 'skills', 'unslop'), { recursive: true });
    writeFileSync(join(plugin, 'skills', 'poteto-mode', 'SKILL.md'), '---\nname: poteto-mode\n---\nUpstream body\n');
    writeFileSync(join(plugin, 'skills', 'poteto-mode', 'references', 'codex-tools.md'), 'Tool mapping\n');
    writeFileSync(join(plugin, 'skills', 'unslop', 'SKILL.md'), 'Sibling dependency\n');
    mkdirSync(join(plugin, 'skills', 'poteto-mode', 'references', 'licenses'));
    writeFileSync(join(plugin, 'skills', 'poteto-mode', 'references', 'licenses', 'LICENSE'), 'Upstream license\n');
    return { root, plugin, target };
}

test('exports upstream bodies and dependencies unchanged with verifiable provenance', context => {
    const { plugin, target } = fixture(context);
    const receipt = exportPstackSkills(plugin, target);
    assert.equal(receipt.skillCount, 2);
    assert.equal(receipt.cloudInvocation, 'unverified');
    assert.equal(receipt.expectedRepositorySkillName, 'poteto-mode');
    for (const [path, hash] of Object.entries(receipt.files)) {
        const exported = readFileSync(join(target, path));
        assert.deepEqual(exported, readFileSync(join(plugin, 'skills', path)));
        assert.equal(createHash('sha256').update(exported).digest('hex'), hash);
    }
    assert.deepEqual(JSON.parse(readFileSync(join(target, 'pstack-export.json'))), receipt);
    assert.equal(readFileSync(join(target, 'PSTACK-LICENSE'), 'utf8'), 'Upstream license\n');
});

test('existing custom skills survive a rejected repeat export', context => {
    const { plugin, target } = fixture(context);
    exportPstackSkills(plugin, target);
    const customPath = join(target, 'poteto-mode', 'SKILL.md');
    writeFileSync(customPath, 'Custom instructions\n');
    assert.throws(() => exportPstackSkills(plugin, target), /already exists/);
    assert.equal(readFileSync(customPath, 'utf8'), 'Custom instructions\n');
});

test('a source symlink is rejected before creating the destination', context => {
    const { plugin, target } = fixture(context);
    symlinkSync(join(plugin, 'skills', 'poteto-mode', 'SKILL.md'), join(plugin, 'skills', 'linked-skill'));
    assert.throws(() => exportPstackSkills(plugin, target), /Unsupported source entry/);
    assert.equal(existsSync(target), false);
});

test('a plugin without the required poteto entry cannot produce a partial export', context => {
    const { plugin, target } = fixture(context);
    rmSync(join(plugin, 'skills', 'poteto-mode', 'SKILL.md'));
    assert.throws(() => exportPstackSkills(plugin, target), /ENOENT/);
    assert.equal(existsSync(target), false);
});
