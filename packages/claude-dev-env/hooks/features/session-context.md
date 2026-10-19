# Session context

This family injects reminders and task guidance when an agent starts, resumes, submits a prompt, spawns a helper, starts an artifact page, or hits an auto mode denial. The startup scripts leave the session quiet when their opt-in conditions fail.

## Checks

- `session/skill_loaded_reminder.py` injects a poteto-mode reminder when the skill needs loading or reloading.
- `session/compaction_recall_prompt.py` returns every message the user typed after a compaction. `session/compaction_user_messages.py` reads them from a Claude Code transcript or a Codex rollout. `session/compaction_trim.py` trims each one in Python: it drops filler, articles, and gratitude, keeps approvals, continuation requests, backtick spans, and paths as typed, and marks a reversed message `(overruled by #N)`. No model runs, so the hook works on Claude Code and Codex with no account.
- `session/task_tool_prompt.py` injects a task tracking directive at session start.
- `session/working_style_prompt.py` injects the session's working style at session start.
- `session/advisor_rules_prompt.py` injects advisor guidance when the built-in advisor is enabled.
- `session/orchestrator_auto_starter.py` injects an orchestrator directive when its environment flag is enabled.
- `session/deepen_first_prompt.py` rewrites a first interactive user task so the worker does the omitted expert job.
- `session/artifact_template_pointer.py` routes an agent that starts an artifact page by scope. A status or progress report prefers the status flowchart from `docs/templates/artifact-page/status-flowchart.html`, unless the person asks for another shape. One flow or one comparison is an inline SVG flowchart with minimal text. A multi-part plan or evidence is an html-plan page from `docs/templates/html-plan/README.md`. When the request names the older artifact page template, it points at `docs/templates/artifact-page/README.md`, which names the tracker template and the diagram template and which ask each fits.
- `advisory/auto_mode_denial_quick_fix.py` proposes one `autoMode.allow` entry and a PowerShell block that writes it after an auto mode denial. It never retries the denied call.

## When it fires

- `session/skill_loaded_reminder.py` runs on `PreToolUse` matcher `Agent|Task` at `10` seconds, `UserPromptSubmit` matcher empty at `10` seconds, `SessionStart` matcher `compact` at `10` seconds, and `SubagentStart` matcher `workflow-subagent` at `10` seconds in `hooks.json`.
- `session/compaction_recall_prompt.py` runs on `SessionStart` matcher `compact` at `10` seconds in `hooks.json`. The installer also writes it to the Codex `hooks.json`, the only `SessionStart` hook Codex gets.
- `session/task_tool_prompt.py`, `session/working_style_prompt.py`, `session/advisor_rules_prompt.py`, and `session/orchestrator_auto_starter.py` run on `SessionStart`, matcher empty, timeout `10` seconds each in `hooks.json`.
- `session/deepen_first_prompt.py` runs on `UserPromptSubmit`, matcher empty, timeout `10` seconds in `hooks.json`.
- In Cursor, `session/deepen_first_prompt.py` also runs on `beforeSubmitPrompt`. Cursor passes that event name to the `UserPromptSubmit` copy it imports from the Claude Code settings too. When both copies run, `session/deepen_turn_marker.py` creates the turn marker only when it does not exist yet, so one copy injects. A later prompt skips when either the transcript marker or the session marker exists, or when the transcript already has a user line in Claude Code's or Cursor's shape.
- `session/artifact_template_pointer.py` runs on `PreToolUse` matcher `Artifact|Skill` at `10` seconds in `hooks.json`. It speaks only on an `Artifact` call with action `quickstart` or a `Skill` call that loads `artifact-design`.
- `advisory/auto_mode_denial_quick_fix.py` runs on `PermissionDenied`, matcher `*`, timeout `10` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. Enable opt-in flags only inside the tests.

- **Skill reminder.** Input is a helper spawn whose prompt lacks poteto-mode. Run `python -m pytest packages/claude-dev-env/hooks/session/test_skill_loaded_reminder.py -q`. The adjacent test observes the reminder and leaves an already prepared prompt unchanged.
- **Compaction recall.** Input is a Claude Code transcript or a Codex rollout with typed, meta, sidechain, peer, and harness entries across a compaction. Run `python -m pytest packages/claude-dev-env/hooks/session/test_compaction_user_messages.py packages/claude-dev-env/hooks/session/test_compaction_trim.py packages/claude-dev-env/hooks/session/test_compaction_recall_prompt.py packages/claude-dev-env/hooks/session/test_compaction_trim_eval.py -q`. The tests observe only typed messages, a stable result across a second compaction, the trim rules, the recall budget, and the trimmed lines in the hook's `additionalContext`. `python packages/claude-dev-env/hooks/session/compaction_trim_eval.py` trims each fixture transcript with planted facts, prints the share of facts that survive, the reversals marked, and the compression ratio, and exits 1 on any loss.
- **Task tracking.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_task_tool_prompt.py -q`. The adjacent test observes a `SessionStart` context directive that names the task tool.
- **Working style.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_working_style_prompt.py -q`. The adjacent test observes the fixed context text.
- **Advisor guidance.** Input is SessionStart with `advisorModel` set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_advisor_rules_prompt.py -q`. The adjacent test observes guidance only when the advisor setting is enabled.
- **Orchestrator start.** Input is SessionStart with its opt-in flag set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_orchestrator_auto_starter.py -q`. The adjacent test observes an orchestrator directive.
- **First-task deepen.** Input is a first UserPromptSubmit task. Run `python -m pytest packages/claude-dev-env/hooks/session/test_deepen_first_prompt.py -q`. The adjacent test observes a skip table, a refusal of the paste path, a rewrite that carries the SCOPE, EXAMPLES, and ZOOM-IN BLOCKER lines, and one injection when two copies see the same Cursor prompt. `python -m pytest packages/claude-dev-env/hooks/session/test_deepen_turn_marker.py -q` observes that only the first marker claim wins. With nothing configured, `deepen_default_rewrite.py` builds that role-shaped rewrite, and `test_deepen_default_rewrite.py` checks the gate accepts it.
- **Artifact template pointer.** Input is an `Artifact` quickstart call. Run `python -m pytest packages/claude-dev-env/hooks/session/test_artifact_template_pointer.py -q`. The adjacent test observes the status flowchart path first, the html-plan path ahead of the template path in `additionalContext`, and silence on a publish call or another skill.
- **Denial quick fix.** Input is a `PermissionDenied` event with a bracketed rule label and a classifier verdict. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_auto_mode_denial_quick_fix.py -q`. The adjacent test observes the named rule, the allow entry, and the PowerShell block; a denial with no verdict gets a note and no block.

## Gotchas

- The recall keeps the first message and the newest that fit in 6,000 characters, under the 2,500 token preview limit Codex applies to hook context. A message over 1,500 characters is cut, and the line says how much was left out.
- The overruled mark comes from cue phrases such as `instead` or `change of plan` and shared words. A reversal with no cue phrase gets no mark, and the later line still overrides by its place. A cue in a message that agrees with an earlier one, such as `dont use haiku` after `use Python trim instead of Haiku`, marks that earlier line too, so the context tells the agent to follow the later message where the two differ.
- `session/skill_loaded_reminder.py` has four registration points. Its tests cover helper prompt rewriting and repeated prompt suppression.
- The advisor prompt depends on settings and an environment disable flag. The two starter scripts each use separate opt-in checks.
- The issue tracker starter requires the checkout to appear in the project path registry.
- `advisory/auto_mode_denial_quick_fix.py` lives under `advisory/` but belongs here because its only output is agent context and a one-line user message.
