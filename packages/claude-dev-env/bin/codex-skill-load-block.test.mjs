import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { lstatSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import {
    PACKAGE_GUIDANCE_BLOCK_END,
    PACKAGE_GUIDANCE_BLOCK_START,
    QUESTION_PRESENTATION_BLOCK_END,
    QUESTION_PRESENTATION_BLOCK_START,
    SKILL_LOAD_BLOCK_END,
    SKILL_LOAD_BLOCK_START,
    SKILL_LOAD_INSTRUCTION,
    removeCodexPackageGuidance,
    removeCodexQuestionGuidance,
    withSkillLoadBlock,
    writeCodexAgentsGuidance,
    writeCodexPackageGuidance,
    writeCodexQuestionGuidance,
} from './codex-skill-load-block.mjs';

const EXPECTED_BLOCK = `${SKILL_LOAD_BLOCK_START}\n${SKILL_LOAD_INSTRUCTION}\n${SKILL_LOAD_BLOCK_END}\n`;
const PACKAGE_GUIDANCE = 'Status\n\nChanged / proof / blocked.\n';
const QUESTION_POLICY = '# Present questions clearly\n\nAsk one question.\n';

function guidanceBlock(guidanceText) {
    return `${PACKAGE_GUIDANCE_BLOCK_START}\n${guidanceText}${PACKAGE_GUIDANCE_BLOCK_END}\n`;
}

function makeHomes(context) {
    const root = mkdtempSync(join(tmpdir(), 'cde-skill-load-'));
    context.after(() => rmSync(root, { recursive: true, force: true }));
    const codexHome = join(root, '.codex');
    const retiredGuidancePath = join(root, '.claude', 'AGENTS.md');
    const sharedGuidancePath = join(root, '.agents', 'AGENTS.md');
    return {
        root,
        codexHome,
        agentsPath: join(codexHome, 'AGENTS.md'),
        retiredGuidancePath,
        sharedGuidancePath,
        allPackageGuidancePaths: [retiredGuidancePath, sharedGuidancePath],
    };
}

function writeGuidance(homes) {
    return writeCodexAgentsGuidance(homes.codexHome, PACKAGE_GUIDANCE, homes.allPackageGuidancePaths);
}

test('the instruction names the skill and binds spawned helpers', () => {
    assert.match(SKILL_LOAD_INSTRUCTION, /pstack:poteto-mode/);
    assert.match(SKILL_LOAD_INSTRUCTION, /spawn_agent/);
});

test('a missing Codex guidance file is created holding the skill-load block and the package guidance', (context) => {
    const homes = makeHomes(context);

    const writtenPath = writeGuidance(homes);

    assert.equal(writtenPath, homes.agentsPath);
    assert.equal(
        readFileSync(homes.agentsPath, 'utf8'),
        `${EXPECTED_BLOCK}\n${guidanceBlock(PACKAGE_GUIDANCE)}`,
    );
});

test('existing guidance keeps every line between the skill-load block and the package guidance', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, '# pstack model configuration\n\nbug-fix: gpt-6-astra\n');

    writeGuidance(homes);

    assert.equal(
        readFileSync(homes.agentsPath, 'utf8'),
        `${EXPECTED_BLOCK}\n# pstack model configuration\n\nbug-fix: gpt-6-astra\n\n${guidanceBlock(PACKAGE_GUIDANCE)}`,
    );
});

test('a repeat install leaves the file unchanged and reports no write', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, 'Custom agents\n');
    writeGuidance(homes);
    const afterFirstInstall = readFileSync(homes.agentsPath, 'utf8');

    assert.equal(writeGuidance(homes), null);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), afterFirstInstall);
});

test('an outdated block is replaced in place and the text around it is kept', () => {
    const outdated = `Intro\n${SKILL_LOAD_BLOCK_START}\nOld wording\n${SKILL_LOAD_BLOCK_END}\nOutro\n`;

    assert.equal(withSkillLoadBlock(outdated), `Intro\n${EXPECTED_BLOCK}Outro\n`);
});

test('a start marker with no end marker gets a fresh block and keeps the stray text', () => {
    const broken = `${SKILL_LOAD_BLOCK_START}\nHalf a block\n`;

    assert.equal(withSkillLoadBlock(broken), `${EXPECTED_BLOCK}\n${broken}`);
});

for (const linkName of ['retiredGuidancePath', 'sharedGuidancePath']) {
    test(`a link to package guidance at ${linkName} becomes a file with both blocks`, (context) => {
        const homes = makeHomes(context);
        mkdirSync(homes.codexHome);
        symlinkSync(homes[linkName], homes.agentsPath);

        const writtenPath = writeGuidance(homes);

        assert.equal(writtenPath, homes.agentsPath);
        assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), false);
        assert.equal(
            readFileSync(homes.agentsPath, 'utf8'),
            `${EXPECTED_BLOCK}\n${guidanceBlock(PACKAGE_GUIDANCE)}`,
        );
    });
}

test('a converted file takes the new package guidance on the next install', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, `${EXPECTED_BLOCK}\n${guidanceBlock('Old guidance\n')}`);

    writeGuidance(homes);

    assert.equal(
        readFileSync(homes.agentsPath, 'utf8'),
        `${EXPECTED_BLOCK}\n${guidanceBlock(PACKAGE_GUIDANCE)}`,
    );
});

test('a link to a file the package does not own is left alone', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    const ownGuidancePath = join(homes.root, 'notes', 'codex.md');
    mkdirSync(join(homes.root, 'notes'));
    writeFileSync(ownGuidancePath, 'My own Codex notes\n');
    symlinkSync(ownGuidancePath, homes.agentsPath);

    assert.equal(writeGuidance(homes), null);
    assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), true);
    assert.equal(readFileSync(ownGuidancePath, 'utf8'), 'My own Codex notes\n');
});

function writePackageGuidance(homes) {
    return writeCodexPackageGuidance(homes.codexHome, PACKAGE_GUIDANCE, homes.allPackageGuidancePaths);
}

test('package guidance creates a missing Codex file holding only the package block', (context) => {
    const homes = makeHomes(context);

    assert.equal(writePackageGuidance(homes), homes.agentsPath);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), guidanceBlock(PACKAGE_GUIDANCE));
});

test('package guidance replaces its block in place and a repeat write changes nothing', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, `Before\n${guidanceBlock('Old guidance\n')}After\n`);

    assert.equal(writePackageGuidance(homes), homes.agentsPath);
    const expectedGuidance = `Before\n${guidanceBlock(PACKAGE_GUIDANCE)}After\n`;
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), expectedGuidance);
    assert.equal(writePackageGuidance(homes), null);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), expectedGuidance);
});

test('package guidance appends its block after custom notes', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, 'Custom agents\n');

    writePackageGuidance(homes);

    assert.equal(
        readFileSync(homes.agentsPath, 'utf8'),
        `Custom agents\n\n${guidanceBlock(PACKAGE_GUIDANCE)}`,
    );
});

for (const linkName of ['retiredGuidancePath', 'sharedGuidancePath']) {
    test(`package guidance turns a link at ${linkName} into a file with only the package block`, (context) => {
        const homes = makeHomes(context);
        mkdirSync(homes.codexHome);
        symlinkSync(homes[linkName], homes.agentsPath);

        assert.equal(writePackageGuidance(homes), homes.agentsPath);
        assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), false);
        assert.equal(readFileSync(homes.agentsPath, 'utf8'), guidanceBlock(PACKAGE_GUIDANCE));
    });
}

test('package guidance leaves a link to a file the package does not own unchanged', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    const ownGuidancePath = join(homes.root, 'notes', 'codex.md');
    mkdirSync(join(homes.root, 'notes'));
    writeFileSync(ownGuidancePath, 'My own Codex notes\n');
    symlinkSync(ownGuidancePath, homes.agentsPath);

    assert.equal(writePackageGuidance(homes), null);
    assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), true);
    assert.equal(readFileSync(ownGuidancePath, 'utf8'), 'My own Codex notes\n');
});

test('package guidance leaves an existing directory and its notes unchanged', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.agentsPath, { recursive: true });
    const notesPath = join(homes.agentsPath, 'notes.md');
    writeFileSync(notesPath, 'Directory notes\n');

    assert.equal(writePackageGuidance(homes), null);
    assert.equal(lstatSync(homes.agentsPath).isDirectory(), true);
    assert.equal(readFileSync(notesPath, 'utf8'), 'Directory notes\n');
});

test('question guidance creates a missing Codex file and repeat writes preserve bytes', (context) => {
    const homes = makeHomes(context);
    const expectedBlock = `${QUESTION_PRESENTATION_BLOCK_START}\n${QUESTION_POLICY}${QUESTION_PRESENTATION_BLOCK_END}\n`;

    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), homes.agentsPath);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), expectedBlock);
    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), null);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), expectedBlock);
});

test('question guidance preserves custom text and replaces only its block', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    const oldBlock = `${QUESTION_PRESENTATION_BLOCK_START}\nOld policy\n${QUESTION_PRESENTATION_BLOCK_END}\n`;
    writeFileSync(homes.agentsPath, `Before\n${oldBlock}After\n`);

    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), homes.agentsPath);
    assert.equal(
        readFileSync(homes.agentsPath, 'utf8'),
        `Before\n${QUESTION_PRESENTATION_BLOCK_START}\n${QUESTION_POLICY}${QUESTION_PRESENTATION_BLOCK_END}\nAfter\n`,
    );
});

test('question guidance appends after custom notes without changing them', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, 'My notes without a final newline');

    writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY);

    assert.ok(readFileSync(homes.agentsPath, 'utf8').startsWith('My notes without a final newline\n\n'));
});

test('question guidance leaves every symlink and its target unchanged', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    mkdirSync(dirname(homes.sharedGuidancePath), { recursive: true });
    writeFileSync(homes.sharedGuidancePath, 'Shared notes\n');
    symlinkSync(homes.sharedGuidancePath, homes.agentsPath);

    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), null);
    assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), true);
    assert.equal(readFileSync(homes.sharedGuidancePath, 'utf8'), 'Shared notes\n');
});

test('question guidance leaves an existing directory and its notes unchanged', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.agentsPath, { recursive: true });
    const notesPath = join(homes.agentsPath, 'notes.md');
    writeFileSync(notesPath, 'Directory notes\n');

    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), null);
    assert.equal(lstatSync(homes.agentsPath).isDirectory(), true);
    assert.equal(readFileSync(notesPath, 'utf8'), 'Directory notes\n');
});

test('a stray question start marker does not consume notes on repeat writes', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    const customNotes = `${QUESTION_PRESENTATION_BLOCK_START}\nIncomplete block\nMy notes\n`;
    writeFileSync(homes.agentsPath, customNotes);

    writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY);
    const firstGuidance = readFileSync(homes.agentsPath, 'utf8');
    assert.ok(firstGuidance.startsWith(customNotes));
    assert.equal(writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY), null);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), firstGuidance);
});

for (const eachGuidance of [
    'Custom guidance\n',
    `${QUESTION_PRESENTATION_BLOCK_START}\nUnfinished policy\nCustom notes\n`,
]) {
    test(`question removal preserves guidance without a complete block ${JSON.stringify(eachGuidance)}`, (context) => {
        const homes = makeHomes(context);
        mkdirSync(homes.codexHome, { recursive: true });
        writeFileSync(homes.agentsPath, eachGuidance);

        assert.equal(removeCodexQuestionGuidance(homes.codexHome), null);
        assert.equal(readFileSync(homes.agentsPath, 'utf8'), eachGuidance);
    });
}

test('question removal preserves a linked file even when its target holds a managed block', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome, { recursive: true });
    const linkedGuidance = `${QUESTION_PRESENTATION_BLOCK_START}\n${QUESTION_POLICY}${QUESTION_PRESENTATION_BLOCK_END}\n`;
    mkdirSync(dirname(homes.sharedGuidancePath), { recursive: true });
    writeFileSync(homes.sharedGuidancePath, linkedGuidance);
    symlinkSync(homes.sharedGuidancePath, homes.agentsPath);

    assert.equal(removeCodexQuestionGuidance(homes.codexHome), null);
    assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), true);
    assert.equal(readFileSync(homes.sharedGuidancePath, 'utf8'), linkedGuidance);
});

test('question removal preserves a guidance directory and its notes', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.agentsPath, { recursive: true });
    const notesPath = join(homes.agentsPath, 'notes.md');
    writeFileSync(notesPath, 'Directory notes\n');

    assert.equal(removeCodexQuestionGuidance(homes.codexHome), null);
    assert.equal(lstatSync(homes.agentsPath).isDirectory(), true);
    assert.equal(readFileSync(notesPath, 'utf8'), 'Directory notes\n');
});

test('package and question removal delete a file left with only blank lines', (context) => {
    const homes = makeHomes(context);
    writePackageGuidance(homes);
    writeCodexQuestionGuidance(homes.codexHome, QUESTION_POLICY);

    assert.equal(removeCodexPackageGuidance(homes.codexHome), homes.agentsPath);
    assert.equal(removeCodexQuestionGuidance(homes.codexHome), homes.agentsPath);
    assert.equal(lstatSync(homes.agentsPath, { throwIfNoEntry: false }), undefined);
});

test('package removal keeps the custom text around its block', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    writeFileSync(homes.agentsPath, `Before\n${guidanceBlock(PACKAGE_GUIDANCE)}After\n`);

    assert.equal(removeCodexPackageGuidance(homes.codexHome), homes.agentsPath);
    assert.equal(readFileSync(homes.agentsPath, 'utf8'), 'Before\nAfter\n');
});

test('package removal leaves a linked file and its target unchanged', (context) => {
    const homes = makeHomes(context);
    mkdirSync(homes.codexHome);
    mkdirSync(dirname(homes.sharedGuidancePath), { recursive: true });
    writeFileSync(homes.sharedGuidancePath, guidanceBlock(PACKAGE_GUIDANCE));
    symlinkSync(homes.sharedGuidancePath, homes.agentsPath);

    assert.equal(removeCodexPackageGuidance(homes.codexHome), null);
    assert.equal(lstatSync(homes.agentsPath).isSymbolicLink(), true);
    assert.equal(readFileSync(homes.sharedGuidancePath, 'utf8'), guidanceBlock(PACKAGE_GUIDANCE));
});

test('question removal leaves a missing guidance file absent', (context) => {
    const homes = makeHomes(context);

    assert.equal(removeCodexQuestionGuidance(homes.codexHome), null);
    assert.equal(lstatSync(homes.agentsPath, { throwIfNoEntry: false }), undefined);
});
