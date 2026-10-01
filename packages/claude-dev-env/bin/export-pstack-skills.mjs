import { createHash } from 'node:crypto';
import { cpSync, lstatSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, mkdtempSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

function inventory(directory, prefix = '') {
    return readdirSync(directory, { withFileTypes: true }).sort((left, right) => left.name.localeCompare(right.name))
        .flatMap(entry => {
            const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
            const entryPath = join(directory, entry.name);
            if (entry.isDirectory()) return inventory(entryPath, relativePath);
            if (!entry.isFile()) throw new Error(`Unsupported source entry: ${relativePath}`);
            return [[relativePath, createHash('sha256').update(readFileSync(entryPath)).digest('hex')]];
        });
}

export function exportPstackSkills(pluginRoot, destination) {
    const source = resolve(pluginRoot);
    const target = resolve(destination);
    const manifest = JSON.parse(readFileSync(join(source, '.codex-plugin', 'plugin.json'), 'utf8'));
    if (manifest.name !== 'pstack' || manifest.skills !== './skills/' || !manifest.version || !manifest.repository) {
        throw new Error('Expected a versioned pstack Codex plugin with a skills directory and repository.');
    }
    if (lstatSync(target, { throwIfNoEntry: false })) throw new Error(`Destination already exists: ${target}`);
    const skillsRoot = join(source, 'skills');
    const poteto = readFileSync(join(skillsRoot, 'poteto-mode', 'SKILL.md'), 'utf8');
    if (!/^name: poteto-mode\r?$/m.test(poteto)) throw new Error('Missing upstream poteto-mode metadata.');
    const files = Object.fromEntries(inventory(skillsRoot));
    const license = readFileSync(join(skillsRoot, 'poteto-mode', 'references', 'licenses', 'LICENSE'));
    const receipt = {
        repository: manifest.repository,
        version: manifest.version,
        sourceManifestSha256: createHash('sha256').update(readFileSync(join(source, '.codex-plugin', 'plugin.json'))).digest('hex'),
        licenseSha256: createHash('sha256').update(license).digest('hex'),
        skillCount: Object.keys(files).filter(path => /^[^/]+\/SKILL\.md$/.test(path)).length,
        expectedRepositorySkillName: 'poteto-mode',
        cloudDiscovery: 'unverified',
        cloudInvocation: 'unverified',
        files,
    };
    mkdirSync(dirname(target), { recursive: true });
    const staging = mkdtempSync(join(dirname(target), '.pstack-export-'));
    try {
        cpSync(skillsRoot, staging, { recursive: true });
        writeFileSync(join(staging, 'PSTACK-LICENSE'), license);
        writeFileSync(join(staging, 'pstack-export.json'), `${JSON.stringify(receipt, null, 2)}\n`);
        if (lstatSync(target, { throwIfNoEntry: false })) throw new Error(`Destination appeared: ${target}`);
        renameSync(staging, target);
    } finally {
        rmSync(staging, { recursive: true, force: true });
    }
    return receipt;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const [pluginRoot, destination, ...extra] = process.argv.slice(2);
    if (!pluginRoot || !destination || extra.length) {
        console.error('Usage: node export-pstack-skills.mjs <plugin-root> <new-repository/.agents/skills>');
        process.exitCode = 1;
    } else {
        try {
            const receipt = exportPstackSkills(pluginRoot, destination);
            console.log(JSON.stringify({ destination: resolve(destination), version: receipt.version, skillCount: receipt.skillCount,
                expectedRepositorySkillName: receipt.expectedRepositorySkillName, cloudDiscovery: receipt.cloudDiscovery,
                cloudInvocation: receipt.cloudInvocation }, null, 2));
        } catch (error) {
            console.error(error.message);
            process.exitCode = 1;
        }
    }
}
