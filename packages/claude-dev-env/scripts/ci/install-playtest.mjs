#!/usr/bin/env node
/**
 * Install playtest: run the shipped package the way a session loads it.
 *
 * The driver installs this package into a scratch home, reads the hook roster
 * the install wrote into `settings.json`, starts one SessionStart hook and one
 * PreToolUse hook from that installed tree against fixture payloads, and reads
 * the output envelope each one returns.
 *
 * Every stage writes the envelope it read to the evidence directory and prints
 * one line carrying the stage name, the artifact path and the artifact's
 * SHA-256 digest::
 *
 *     every stage read the envelope it expected -> exit 0
 *     one stage read something else             -> exit 1
 *
 * Usage::
 *
 *     node scripts/ci/install-playtest.mjs
 *     node scripts/ci/install-playtest.mjs --home <dir> --evidence <dir>
 *     node scripts/ci/install-playtest.mjs --home <dir> --skip-install
 *
 * `--home` names the scratch home to install into and keeps it after the run.
 * `--skip-install` grades the tree already installed in that home, which is how
 * a broken install is read back.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import {
    createScratchHome,
    removeScratchHome,
    runInstaller,
    scratchHomeEnvironment,
    SANDBOX_GIT_CONFIG_BODY,
    SANDBOX_GIT_CONFIG_NAME,
} from './scratch-home-install.mjs';

export const EVIDENCE_PREFIX = 'cde-playtest-';
export const SETTINGS_RELATIVE_PATH = join('.claude', 'settings.json');
export const HOOK_TIMEOUT_MILLISECONDS = 60_000;
export const PASS_MARK = 'PASS';
export const FAIL_MARK = 'FAIL';
export const DIGEST_ALGORITHM = 'sha256';
export const INSTALL_STAGE_NAME = 'install';
export const SESSION_START_STAGE_NAME = 'session_start_hook';
export const BLOCKING_STAGE_NAME = 'blocking_hook';
export const SESSION_START_EVENT_NAME = 'SessionStart';
export const PRE_TOOL_USE_EVENT_NAME = 'PreToolUse';
export const SESSION_START_HOOK_SCRIPT_NAME = 'working_style_prompt.py';
export const BASH_HOOK_SCRIPT_NAME = 'bash_pre_tool_use_dispatcher.py';
export const BASH_MATCHER = 'Bash';
export const USER_PROMPT_SUBMIT_EVENT_NAME = 'UserPromptSubmit';
export const DEEPEN_HOOK_SCRIPT_NAME = 'deepen_first_prompt.py';
export const NESTED_HOOK_SCRIPT_NAME = 'nested_project_hooks.py';
export const DEEPEN_MARKER = 'CDE_DEEPEN:v1';
export const DEEPEN_AGENT_MARKER = 'CDE_DEEPEN_AGENT';
export const DEEPEN_STAGE_NAME = 'deepen_first_prompt';
export const DEEPEN_SKIP_STAGE_NAME = 'deepen_skips';
export const DEEPEN_REWRITE_STAGE_NAME = 'deepen_mod_text';
export const DEEPEN_NESTED_STAGE_NAME = 'deepen_nested_home';
export const DEEPEN_CLOUD_GAP_STAGE_NAME = 'deepen_cloud_gaps';
export const DEEPEN_STUB_REWRITE = [
    'Omitted: ship contrast tokens with the theme.',
    'Source: src/settings/theme.ts',
    'Methods: existing token file and a visual check.',
    'Proof: screenshot of the settings page in dark mode.',
].join('\n');
export const CLAUDE_SUBAGENT_PROMPT_PREFIX = (
    'Before any other work, invoke the poteto-mode skill with the Skill tool. '
    + 'Every prompt you write for a subagent opens with the same instruction.'
);
export const CLOUD_GAP_EVIDENCE = {
    cursorCloud: {
        doc: 'https://cursor.com/docs/hooks',
        quotes: [
            'User-level hooks (`~/.cursor/hooks.json`) are not available in cloud agents. Cloud agent VMs don\'t have access to your local home directory configuration.',
            'sessionStart: Deferred while cloud agents can still start in a read-only environment. Hooks don\'t load there, so a cloud sessionStart would fire too late (after the first write) rather than at true session start.',
            'beforeSubmitPrompt output is continue and user_message only.',
        ],
        path: 'the deepen skill under ~/.cursor/skills',
    },
    codexCloud: {
        doc: 'https://learn.chatgpt.com/docs/hooks',
        quotes: [
            'Command/shell, prompt, and agent handlers; hooks from local configuration, plugins, or local directories; environment-scoped hooks; and SessionEnd MCP hooks are not supported with cloud orchestration, even when tools execute locally.',
        ],
    },
    claudeUserPromptSubmit: {
        doc: 'https://code.claude.com/docs/en/hooks',
        quotes: [
            'UserPromptSubmit: can\'t replace the prompt; it only injects additionalContext alongside it',
        ],
    },
    claudePromptSubmitMod: {
        doc: 'https://code.claude.com/docs/en/plugins/mods/events',
        quotes: [
            'Rewrite the prompt. The transcript and your prompt history show the new text. next({ ...e, text: newText })',
            'A cloud session: Yes, for a plugin that reaches the cloud session. This package still keeps the Python hook as the cloud fallback because mods that replace settings hooks stay off when CLAUDE_CODE_REMOTE is true.',
        ],
    },
};

export const SESSION_START_PAYLOAD = {
    hook_event_name: SESSION_START_EVENT_NAME,
    source: 'startup',
};

export const BASH_HOOK_PAYLOAD = {
    tool_name: BASH_MATCHER,
    tool_input: { command: 'git show origin/main:.claude/settings.json' },
};

export const REWRITE_MARKER = 'MSYS2_ARG_CONV_EXCL';

/**
 * Parse the driver's arguments.
 *
 * @param {string[]} argv Arguments after the script name.
 * @returns {{homePath: string | null, evidencePath: string | null, shouldSkipInstall: boolean}} The parsed options.
 */
export function parseArguments(argv) {
    let homePath = null;
    let evidencePath = null;
    let shouldSkipInstall = false;
    for (let index = 0; index < argv.length; index += 1) {
        const token = argv[index];
        if (token === '--home') {
            homePath = argv[index + 1] ?? null;
            index += 1;
        } else if (token === '--evidence') {
            evidencePath = argv[index + 1] ?? null;
            index += 1;
        } else if (token === '--skip-install') {
            shouldSkipInstall = true;
        }
    }
    return { homePath, evidencePath, shouldSkipInstall };
}

/**
 * Read the SHA-256 digest of a file.
 *
 * @param {string} filePath Path of the file to digest.
 * @returns {string} The hexadecimal digest.
 */
export function fileDigest(filePath) {
    return createHash(DIGEST_ALGORITHM).update(readFileSync(filePath)).digest('hex');
}

/**
 * Read every hook command the installed settings file declares for one event.
 *
 * @param {string} settingsPath Path of the installed settings file.
 * @param {string} eventName Hook event name, such as `SessionStart`.
 * @returns {{matcher: string, command: string}[]} Each declared hook command.
 */
export function hookCommandsForEvent(settingsPath, eventName) {
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8'));
    const allMatcherGroups = settings.hooks?.[eventName] ?? [];
    const allCommands = [];
    for (const eachGroup of allMatcherGroups) {
        for (const eachHook of eachGroup.hooks ?? []) {
            if (typeof eachHook.command !== 'string') continue;
            allCommands.push({ matcher: eachGroup.matcher ?? '', command: eachHook.command });
        }
    }
    return allCommands;
}

/**
 * Select the one installed hook command a stage drives.
 *
 * @param {{matcher: string, command: string}[]} allCommands Declared hook commands.
 * @param {string} scriptName Basename of the hook script the stage drives.
 * @returns {string} The command line the install wrote.
 * @throws {Error} The installed roster declares no such hook.
 */
export function selectHookCommand(allCommands, scriptName) {
    const selected = allCommands.find((each) => each.command.includes(scriptName));
    if (!selected) {
        throw new Error(`The installed hook roster declares no ${scriptName}`);
    }
    return selected.command;
}

/**
 * Run one installed hook command against a payload and return its output.
 *
 * @param {string} command The command line the install wrote.
 * @param {string} scratchHome Scratch home the install wrote into.
 * @param {object} payload The hook payload written to standard input.
 * @returns {{status: number | null, stdout: string, stderr: string}} The hook's result.
 */
export function runInstalledHook(command, scratchHome, payload, extraEnvironment = {}) {
    const hookProcess = spawnSync(command, {
        shell: true,
        input: JSON.stringify(payload),
        encoding: 'utf8',
        cwd: scratchHome,
        timeout: HOOK_TIMEOUT_MILLISECONDS,
        env: { ...scratchHomeEnvironment(scratchHome), ...extraEnvironment },
    });
    return {
        status: hookProcess.status,
        stdout: hookProcess.stdout ?? '',
        stderr: hookProcess.stderr ?? '',
    };
}

/**
 * Read a hook's standard output as an envelope for one event.
 *
 * @param {string} stdout The hook's standard output.
 * @param {string} eventName The event name the envelope must name.
 * @returns {object} The `hookSpecificOutput` object.
 * @throws {Error} The output is not an envelope for that event.
 */
export function readEnvelope(stdout, eventName) {
    const trimmed = stdout.trim();
    if (!trimmed) {
        throw new Error(`The hook wrote no ${eventName} envelope`);
    }
    const parsed = JSON.parse(trimmed);
    const hookSpecificOutput = parsed.hookSpecificOutput;
    if (!hookSpecificOutput || hookSpecificOutput.hookEventName !== eventName) {
        throw new Error(`The hook envelope names ${hookSpecificOutput?.hookEventName} rather than ${eventName}`);
    }
    return hookSpecificOutput;
}

function writeEvidence(evidenceDirectory, stageName, body) {
    const evidencePath = join(evidenceDirectory, `${stageName}.json`);
    writeFileSync(evidencePath, `${body}\n`);
    return evidencePath;
}

function reportStage(stageName, evidencePath) {
    process.stdout.write(`[${PASS_MARK}] playtest ${stageName} ${evidencePath} ${DIGEST_ALGORITHM}=${fileDigest(evidencePath)}\n`);
}

function reportFailure(stageName, detail) {
    process.stdout.write(`[${FAIL_MARK}] playtest ${stageName} ${detail}\n`);
}

function runInstallStage(scratchHome, evidenceDirectory, shouldSkipInstall) {
    if (!shouldSkipInstall) {
        const install = runInstaller(scratchHome, []);
        if (install.status !== 0) {
            throw new Error(`The installer exited ${install.status}: ${install.stderr.trim()}`);
        }
    }
    const settingsPath = join(scratchHome, SETTINGS_RELATIVE_PATH);
    if (!existsSync(settingsPath)) {
        throw new Error(`The install wrote no ${settingsPath}`);
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        INSTALL_STAGE_NAME,
        JSON.stringify({ settingsPath, digest: fileDigest(settingsPath) }),
    );
    reportStage(INSTALL_STAGE_NAME, evidencePath);
    return settingsPath;
}

function runSessionStartStage(settingsPath, scratchHome, evidenceDirectory) {
    const command = selectHookCommand(
        hookCommandsForEvent(settingsPath, SESSION_START_EVENT_NAME),
        SESSION_START_HOOK_SCRIPT_NAME,
    );
    const hookResult = runInstalledHook(command, scratchHome, SESSION_START_PAYLOAD);
    const envelope = readEnvelope(hookResult.stdout, SESSION_START_EVENT_NAME);
    if (typeof envelope.additionalContext !== 'string' || envelope.additionalContext.length === 0) {
        throw new Error('The SessionStart envelope carries no additionalContext');
    }
    if (envelope.additionalContext.includes(DEEPEN_MARKER)) {
        throw new Error('The SessionStart envelope repeated first-task deepen text');
    }
    const evidencePath = writeEvidence(evidenceDirectory, SESSION_START_STAGE_NAME, JSON.stringify(envelope));
    reportStage(SESSION_START_STAGE_NAME, evidencePath);
}

function userPromptPayload(prompt, transcriptPath) {
    const payload = {
        hook_event_name: USER_PROMPT_SUBMIT_EVENT_NAME,
        prompt,
        session_id: 'playtest-session',
    };
    if (transcriptPath) payload.transcript_path = transcriptPath;
    return payload;
}

function deepenHookEnvironment(extraEnvironment = {}) {
    return {
        CDE_DEEPEN_REWRITE: DEEPEN_STUB_REWRITE,
        ...extraEnvironment,
    };
}

function parseJsonDecision(stdout) {
    const trimmed = stdout.trim();
    if (!trimmed) return { decision: 'silent' };
    return JSON.parse(trimmed);
}

function runDeepenFirstTaskStage(settingsPath, scratchHome, evidenceDirectory) {
    const command = selectHookCommand(
        hookCommandsForEvent(settingsPath, USER_PROMPT_SUBMIT_EVENT_NAME),
        DEEPEN_HOOK_SCRIPT_NAME,
    );
    const transcriptPath = join(evidenceDirectory, 'first-task.jsonl');
    const extraEnvironment = deepenHookEnvironment();
    const envelopeResult = runInstalledHook(
        command,
        scratchHome,
        userPromptPayload('Add dark mode to the settings page', transcriptPath),
        extraEnvironment,
    );
    const envelope = readEnvelope(envelopeResult.stdout, USER_PROMPT_SUBMIT_EVENT_NAME);
    if (!String(envelope.additionalContext || '').includes(DEEPEN_MARKER)) {
        throw new Error('The UserPromptSubmit envelope carries no deepen marker');
    }
    if (!String(envelope.additionalContext).includes('src/settings/theme.ts')) {
        throw new Error('The UserPromptSubmit envelope omitted the stub source');
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        DEEPEN_STAGE_NAME,
        JSON.stringify(envelope),
    );
    reportStage(DEEPEN_STAGE_NAME, evidencePath);
    return { command, transcriptPath };
}

function runDeepenRewriteStage(command, scratchHome, evidenceDirectory) {
    const transcriptPath = join(evidenceDirectory, 'mod-text.jsonl');
    const hookResult = runInstalledHook(
        command,
        scratchHome,
        userPromptPayload('Add dark mode to the settings page', transcriptPath),
        deepenHookEnvironment({ CDE_DEEPEN_OUTPUT: 'rewrite' }),
    );
    const printed = hookResult.stdout;
    if (!printed.startsWith(DEEPEN_MARKER)) {
        throw new Error(`The rewrite output did not start with ${DEEPEN_MARKER}`);
    }
    if (printed.includes('hookSpecificOutput')) {
        throw new Error('The Claude mod rewrite printed a command-hook envelope');
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        DEEPEN_REWRITE_STAGE_NAME,
        JSON.stringify({ stdout: printed }),
    );
    reportStage(DEEPEN_REWRITE_STAGE_NAME, evidencePath);
}

function runDeepenSkipStage(command, scratchHome, evidenceDirectory, firstTranscriptPath) {
    const jsonEnvironment = deepenHookEnvironment({ CDE_DEEPEN_OUTPUT: 'json' });
    const cases = [
        {
            name: 'thanks',
            payload: userPromptPayload('thanks', join(evidenceDirectory, 'thanks.jsonl')),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'trivial' },
        },
        {
            name: 'slash',
            payload: userPromptPayload('/sr-loop', join(evidenceDirectory, 'slash.jsonl')),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'slash-command' },
        },
        {
            name: 'spawn',
            payload: userPromptPayload(
                `${CLAUDE_SUBAGENT_PROMPT_PREFIX}\n\nReply leaf.`,
                join(evidenceDirectory, 'spawn.jsonl'),
            ),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'spawn-rewrite' },
        },
        {
            name: 'skip-flag',
            payload: userPromptPayload('Add dark mode to the settings page', join(evidenceDirectory, 'skip-flag.jsonl')),
            extraEnvironment: deepenHookEnvironment({ CDE_DEEPEN_OUTPUT: 'json', CDE_SKIP_DEEPEN: '1' }),
            expected: { decision: 'skip', reason: 'skip-flag' },
        },
        {
            name: 'later-turn',
            payload: userPromptPayload('and also the billing page', firstTranscriptPath),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'later-turn' },
        },
        {
            name: 'marker',
            payload: userPromptPayload(`${DEEPEN_MARKER}\n\nDo the job.`, join(evidenceDirectory, 'marker.jsonl')),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'marker-present' },
        },
        {
            name: 'loop',
            payload: userPromptPayload('/loop until tests pass', join(evidenceDirectory, 'loop.jsonl')),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'loop-or-helper' },
        },
        {
            name: 'deepen-agent',
            payload: userPromptPayload(
                `${DEEPEN_AGENT_MARKER}\nAnswer the four deepening questions.`,
                join(evidenceDirectory, 'agent.jsonl'),
            ),
            extraEnvironment: jsonEnvironment,
            expected: { decision: 'skip', reason: 'deepen-agent' },
        },
    ];
    const results = [];
    for (const eachCase of cases) {
        const hookResult = runInstalledHook(
            command,
            scratchHome,
            eachCase.payload,
            eachCase.extraEnvironment,
        );
        const decision = parseJsonDecision(hookResult.stdout);
        if (decision.decision !== eachCase.expected.decision || decision.reason !== eachCase.expected.reason) {
            throw new Error(
                `Skip ${eachCase.name} returned ${JSON.stringify(decision)} expected ${JSON.stringify(eachCase.expected)}`,
            );
        }
        results.push({ name: eachCase.name, decision });
    }
    const silentThanks = runInstalledHook(
        command,
        scratchHome,
        userPromptPayload('thanks', join(evidenceDirectory, 'thanks-silent.jsonl')),
        deepenHookEnvironment(),
    );
    if (silentThanks.stdout.trim() !== '') {
        throw new Error('A skipped prompt printed command-hook output');
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        DEEPEN_SKIP_STAGE_NAME,
        JSON.stringify({ results, silentThanks: silentThanks.stdout }),
    );
    reportStage(DEEPEN_SKIP_STAGE_NAME, evidencePath);
}

function runDeepenNestedStage(settingsPath, scratchHome, evidenceDirectory) {
    const nestedCommand = selectHookCommand(
        hookCommandsForEvent(settingsPath, USER_PROMPT_SUBMIT_EVENT_NAME),
        NESTED_HOOK_SCRIPT_NAME,
    );
    const deepenCommand = selectHookCommand(
        hookCommandsForEvent(settingsPath, USER_PROMPT_SUBMIT_EVENT_NAME),
        DEEPEN_HOOK_SCRIPT_NAME,
    );
    const sessionDirectory = join(evidenceDirectory, 'nested-session');
    const checkoutDirectory = join(sessionDirectory, 'alpha');
    mkdirSync(join(checkoutDirectory, '.git'), { recursive: true });
    mkdirSync(join(checkoutDirectory, '.claude'), { recursive: true });
    writeFileSync(
        join(checkoutDirectory, '.claude', 'settings.json'),
        `${JSON.stringify({
            hooks: {
                UserPromptSubmit: [
                    {
                        matcher: '',
                        hooks: [{ type: 'command', command: deepenCommand, timeout: 10 }],
                    },
                ],
            },
        }, null, 2)}\n`,
    );
    const hookResult = spawnSync(nestedCommand, {
        shell: true,
        input: JSON.stringify(userPromptPayload(
            'Add dark mode to the settings page',
            join(evidenceDirectory, 'nested.jsonl'),
        )),
        encoding: 'utf8',
        cwd: sessionDirectory,
        timeout: HOOK_TIMEOUT_MILLISECONDS,
        env: {
            ...scratchHomeEnvironment(scratchHome),
            ...deepenHookEnvironment(),
            CLAUDE_PROJECT_DIR: sessionDirectory,
        },
    });
    const envelope = readEnvelope(hookResult.stdout, USER_PROMPT_SUBMIT_EVENT_NAME);
    if (!String(envelope.additionalContext || '').includes(DEEPEN_MARKER)) {
        throw new Error('The nested home-folder session carried no deepen marker');
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        DEEPEN_NESTED_STAGE_NAME,
        JSON.stringify(envelope),
    );
    reportStage(DEEPEN_NESTED_STAGE_NAME, evidencePath);
}

function runDeepenInstallSurfaceStage(scratchHome, evidenceDirectory) {
    const settingsPath = join(scratchHome, SETTINGS_RELATIVE_PATH);
    const userPromptCommands = hookCommandsForEvent(settingsPath, USER_PROMPT_SUBMIT_EVENT_NAME);
    if (!userPromptCommands.some((each) => each.command.includes(DEEPEN_HOOK_SCRIPT_NAME))) {
        throw new Error('The installed Claude settings declare no deepen_first_prompt.py');
    }
    const codexHooksPath = join(scratchHome, '.codex', 'hooks.json');
    const codexHooks = JSON.parse(readFileSync(codexHooksPath, 'utf8'));
    const codexUserPrompt = JSON.stringify(codexHooks.hooks?.UserPromptSubmit ?? []);
    if (!codexUserPrompt.includes(DEEPEN_HOOK_SCRIPT_NAME)) {
        throw new Error('The installed Codex hooks declare no UserPromptSubmit deepen_first_prompt.py');
    }
    const cursorSkillPath = join(scratchHome, '.cursor', 'skills', 'deepen', 'SKILL.md');
    if (!existsSync(cursorSkillPath)) {
        throw new Error(`The install wrote no ${cursorSkillPath}`);
    }
    const codexAgentsPath = join(scratchHome, '.codex', 'AGENTS.md');
    const codexAgentsText = existsSync(codexAgentsPath) ? readFileSync(codexAgentsPath, 'utf8') : '';
    if (!codexAgentsText.includes('<!-- claude-dev-env deepen: start -->')) {
        throw new Error('The installed Codex AGENTS.md carries no deepen guidance block');
    }
    const evidencePath = writeEvidence(
        evidenceDirectory,
        'deepen_install_surfaces',
        JSON.stringify({
            claudeUserPromptSubmit: userPromptCommands.map((each) => each.command),
            codexUserPromptSubmit: codexHooks.hooks.UserPromptSubmit,
            cursorSkillPath,
            codexAgentsPath,
        }),
    );
    reportStage('deepen_install_surfaces', evidencePath);
}

function runDeepenCloudGapStage(evidenceDirectory) {
    const evidencePath = writeEvidence(
        evidenceDirectory,
        DEEPEN_CLOUD_GAP_STAGE_NAME,
        JSON.stringify(CLOUD_GAP_EVIDENCE),
    );
    reportStage(DEEPEN_CLOUD_GAP_STAGE_NAME, evidencePath);
}

function runBlockingStage(settingsPath, scratchHome, evidenceDirectory) {
    const command = selectHookCommand(
        hookCommandsForEvent(settingsPath, PRE_TOOL_USE_EVENT_NAME),
        BASH_HOOK_SCRIPT_NAME,
    );
    const hookResult = runInstalledHook(command, scratchHome, BASH_HOOK_PAYLOAD);
    const envelope = readEnvelope(hookResult.stdout, PRE_TOOL_USE_EVENT_NAME);
    if (envelope.permissionDecision !== undefined) {
        throw new Error(`The PreToolUse envelope skipped the permission prompt with ${envelope.permissionDecision}`);
    }
    const rewrittenCommand = envelope.updatedInput?.command ?? '';
    if (!rewrittenCommand.includes(REWRITE_MARKER)) {
        throw new Error(`The PreToolUse envelope left the command unrewritten: ${rewrittenCommand}`);
    }
    const evidencePath = writeEvidence(evidenceDirectory, BLOCKING_STAGE_NAME, JSON.stringify(envelope));
    reportStage(BLOCKING_STAGE_NAME, evidencePath);
}

/**
 * Run every playtest stage and return the driver's exit code.
 *
 * @param {string[]} argv Arguments after the script name.
 * @returns {number} Zero when every stage read the envelope it expected.
 */
export function runPlaytest(argv) {
    const options = parseArguments(argv);
    const scratchHome = options.homePath ?? createScratchHome();
    if (options.homePath) {
        mkdirSync(scratchHome, { recursive: true });
        const gitConfigPath = join(scratchHome, SANDBOX_GIT_CONFIG_NAME);
        if (!existsSync(gitConfigPath)) {
            writeFileSync(gitConfigPath, SANDBOX_GIT_CONFIG_BODY);
        }
    }
    const evidenceDirectory = options.evidencePath ?? mkdtempSync(join(tmpdir(), EVIDENCE_PREFIX));
    mkdirSync(evidenceDirectory, { recursive: true });
    let stageName = INSTALL_STAGE_NAME;
    try {
        const settingsPath = runInstallStage(scratchHome, evidenceDirectory, options.shouldSkipInstall);
        stageName = SESSION_START_STAGE_NAME;
        runSessionStartStage(settingsPath, scratchHome, evidenceDirectory);
        stageName = BLOCKING_STAGE_NAME;
        runBlockingStage(settingsPath, scratchHome, evidenceDirectory);
        stageName = 'deepen_install_surfaces';
        runDeepenInstallSurfaceStage(scratchHome, evidenceDirectory);
        stageName = DEEPEN_STAGE_NAME;
        const deepen = runDeepenFirstTaskStage(settingsPath, scratchHome, evidenceDirectory);
        stageName = DEEPEN_REWRITE_STAGE_NAME;
        runDeepenRewriteStage(deepen.command, scratchHome, evidenceDirectory);
        stageName = DEEPEN_SKIP_STAGE_NAME;
        runDeepenSkipStage(deepen.command, scratchHome, evidenceDirectory, deepen.transcriptPath);
        stageName = DEEPEN_NESTED_STAGE_NAME;
        runDeepenNestedStage(settingsPath, scratchHome, evidenceDirectory);
        stageName = DEEPEN_CLOUD_GAP_STAGE_NAME;
        runDeepenCloudGapStage(evidenceDirectory);
    } catch (error) {
        reportFailure(stageName, error instanceof Error ? error.message : String(error));
        return 1;
    } finally {
        if (!options.homePath) {
            removeScratchHome(scratchHome);
        }
    }
    process.stdout.write('install playtest: every stage read its envelope\n');
    return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    process.exit(runPlaytest(process.argv.slice(2)));
}
