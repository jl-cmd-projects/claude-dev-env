---
name: build-eval
description: >-
  Evaluate skills with a bounded direct Codex review suite or `claude plugin eval`.
  Use labeled inputs and deterministic grading for output correctness; use a plugin
  wrapper and with/without-plugin comparisons for discovery and contribution.
  Use when the user asks to eval or test a skill.
---

# Build eval

For building an evaluation of an AI workflow, follow [the design process](reference/build-evaluation.md).
For a direct Codex output-quality evaluation, use [the review suite](evals/review/README.md).
It includes labeled cases, executable witnesses, related-group holdouts, a bounded
`codex exec` adapter, stored replay, trace capture and deterministic precision/recall
grading. Start with its validation command and two-case smoke. Preserve the distinction
between grader validation, stored replay, a fresh recipe run and a complete workflow run.
Use the plugin process below when measuring skill discovery or with/without-plugin contribution.

## Contents

- Principle
- Gotchas
- When this applies
- Process
- Files

## Principle

`claude plugin eval` runs plugins only. Wrap the skill in a plugin folder whose layout keeps every
relative link working. Grade behavior only the skill produces. Judge the skill by the delta between
the arm with the plugin and the arm without it.

## Gotchas

- A `.claude-plugin/plugin.json` under any skills directory turns that folder into a
  `<name>@skills-dir` plugin in every session. Build the wrapper outside every skills directory.
- The run sandbox gets a throwaway home and config. User settings, hooks, CLAUDE.md, MCP servers,
  memory, and other skills are absent. Plugin items carry a prefix, such as `<plugin>:session-advisor`.
- `claude plugin eval init` with no arguments is interactive and needs a terminal. From an agent
  shell, run `claude plugin eval init --bare <case-name>`.
- A prompt that starts with `/skill-name` loads the skill with no `Skill` tool call, so
  `tool_used: Skill` always fails on a slash case.
- A plain-words case triggers only when the skill allows model invocation. Leave
  `disable-model-invocation` unset in the copied frontmatter.
- Write, Edit, SendMessage, and Bash need `--allow-tools` on the command line. Bash and PowerShell
  grants refuse the run on native Windows, which has no sandbox backend. Run those cases under WSL2.
- Writes under a loaded `--plugin-dir` are denied in dontAsk mode. That skews the with-plugin arm
  only, so keep every working and output folder outside the plugin root.
- A metric built from tool_use attempts reports success even when every write was denied. Read each
  run's `permission_denials` and final result before you compare arms.
- A score under `--ablation none` says nothing about what the skill adds. Run the baseline once
  before you claim the skill helps.
- The sandbox disables feature-flag fetching. Flag-gated features such as the built-in `advisor()`
  tool are off, and `/advisor` replies "isn't available in this environment". No env var or plugin
  setting turns them on. Plugin `settings.json` accepts only `agent` and `subagentStatusLine`. Test
  such a feature with the `claude -p` recipe in `reference/graders-and-commands.md`.
- `--keep-temp` on Windows warns that it cannot seal the folder. Delete that folder when done with
  PowerShell `Remove-Item -Recurse -Force -LiteralPath <path>`.
- A loop the user asks to run until clean runs with no round cap and no retry cap. Use only the
  limits the user set. Name any other stop condition to the user before the first launch, and
  report each run it ended as stopped by that condition.

## When this applies

Use this skill to measure whether a skill that is not packaged as a plugin triggers and changes
behavior. It needs Claude Code 2.1.269 or later. Source doc: https://code.claude.com/docs/en/plugin-evals

## Process

When the host exposes a task tool, register one session task per numbered step.
Otherwise work the steps in order.

1. Run `claude --version` and confirm 2.1.269 or later.
2. Create the wrapper folder outside every skills directory:

   ```text
   <wrapper>/
   ├── .claude-plugin/
   │   └── plugin.json
   ├── skills/
   │   └── <name>/
   ├── agents/
   └── <each shared doc, at the path the skill's relative links expect>
   ```

   `plugin.json` holds `name`, `version`, and `description`.
3. Copy the skill, every agent it spawns, and every shared doc it links. Copy from a tree at
   `origin/main`, not from a stale worktree. Resolve each relative link in the copied skill against
   the wrapper root.
4. In the wrapper root, run `claude plugin eval init --bare <case-name>` once per case.
5. Write `evals/<case>/prompt.md` and `evals/<case>/graders/*.md` for each case. Frontmatter keys,
   grader types, and the case set are in `reference/graders-and-commands.md`.
6. Re-copy the skill from `origin/main`, then run the smoke command from the reference file.
7. Read each run's `permission_denials` and final result. Fix any denial that the case needs.
8. Re-copy the skill, then run the full eval. Read the delta in `aggregate-result.json`.
9. Delete any `--keep-temp` sandbox folder.

## Files

- `SKILL.md`. Wrapper layout, gotchas, and process.
- `reference/graders-and-commands.md`. Prompt frontmatter, grader types, case set, eval commands,
  and the `claude -p` recipe for flag-gated features.

```text
build-eval/
├── SKILL.md
└── reference/
    └── graders-and-commands.md
```
