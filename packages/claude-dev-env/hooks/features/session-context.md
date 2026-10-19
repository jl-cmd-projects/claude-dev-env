# Session context

This family injects reminders and task guidance when an agent starts, resumes, submits a prompt, spawns a helper, starts an artifact page, or hits an auto mode denial. The startup scripts leave the session quiet when their opt-in conditions fail.

## Checks

- `session/skill_loaded_reminder.py` injects a poteto-mode reminder when the skill needs loading or reloading.
- `session/compaction_recall_prompt.py` tells the agent after a compaction to run `session/compaction_user_messages.py` on its transcript. That command writes every message the user typed to `~/.claude/compaction-recall/<session>.md` and prints only the path. A PostToolUse agent hook reads the file and returns the messages in caveman style as its block reason. The trim rules sit in the hook prompt, since the hook model treats file text as data.
- `session/task_tool_prompt.py` injects a task tracking directive at session start.
- `session/working_style_prompt.py` injects the session's working style at session start.
- `session/advisor_rules_prompt.py` injects advisor guidance when the built-in advisor is enabled.
- `session/orchestrator_auto_starter.py` injects an orchestrator directive when its environment flag is enabled.
- `session/deepen_first_prompt.py` rewrites a first interactive user task so the worker does the omitted expert job.
- `session/artifact_template_pointer.py` routes an agent that starts an artifact page by scope. A status or progress report prefers the status flowchart from `docs/templates/artifact-page/status-flowchart.html`, unless the person asks for another shape. One flow or one comparison is an inline SVG flowchart with minimal text. A multi-part plan or evidence is an html-plan page from `docs/templates/html-plan/README.md`. When the request names the older artifact page template, it points at `docs/templates/artifact-page/README.md`, which names the tracker template and the diagram template and which ask each fits.
- `advisory/auto_mode_denial_quick_fix.py` proposes one `autoMode.allow` entry and a PowerShell block that writes it after an auto mode denial. It never retries the denied call.

## When it fires

- `session/skill_loaded_reminder.py` runs on `PreToolUse` matcher `Agent|Task` at `10` seconds, `UserPromptSubmit` matcher empty at `10` seconds, `SessionStart` matcher `compact` at `10` seconds, and `SubagentStart` matcher `workflow-subagent` at `10` seconds in `hooks.json`.
- `session/compaction_recall_prompt.py` runs on `SessionStart` matcher `compact` at `10` seconds in `hooks.json`. The condensing hook is a `type: "agent"` hook on `PostToolUse` matcher `Bash`, with `if` set to `Bash(*compaction_user_messages.py*)`, model `haiku`, and a `180` second timeout. The hook's Read call obeys session permissions, so the package `settings.json` allows `Read(~/.claude/compaction-recall/**)`.
- `session/task_tool_prompt.py`, `session/working_style_prompt.py`, `session/advisor_rules_prompt.py`, and `session/orchestrator_auto_starter.py` run on `SessionStart`, matcher empty, timeout `10` seconds each in `hooks.json`.
- `session/deepen_first_prompt.py` runs on `UserPromptSubmit`, matcher empty, timeout `10` seconds in `hooks.json`.
- In Cursor, `session/deepen_first_prompt.py` also runs on `beforeSubmitPrompt`. Cursor passes that event name to the `UserPromptSubmit` copy it imports from the Claude Code settings too. When both copies run, `session/deepen_turn_marker.py` creates the turn marker only when it does not exist yet, so one copy injects. A later prompt skips when either the transcript marker or the session marker exists, or when the transcript already has a user line in Claude Code's or Cursor's shape.
- `session/artifact_template_pointer.py` runs on `PreToolUse` matcher `Artifact|Skill` at `10` seconds in `hooks.json`. It speaks only on an `Artifact` call with action `quickstart` or a `Skill` call that loads `artifact-design`.
- `advisory/auto_mode_denial_quick_fix.py` runs on `PermissionDenied`, matcher `*`, timeout `10` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. Enable opt-in flags only inside the tests.

- **Skill reminder.** Input is a helper spawn whose prompt lacks poteto-mode. Run `python -m pytest packages/claude-dev-env/hooks/session/test_skill_loaded_reminder.py -q`. The adjacent test observes the reminder and leaves an already prepared prompt unchanged.
- **Compaction recall.** Input is a transcript with typed, meta, sidechain, peer, and harness entries across a compaction. Run `python -m pytest packages/claude-dev-env/hooks/session/test_compaction_user_messages.py packages/claude-dev-env/hooks/session/test_compaction_recall_prompt.py -q`. The tests observe only typed messages in the file, a stable result across a second compaction, only the path on stdout, and an `if` rule that matches the command the recall names. `python packages/claude-dev-env/hooks/session/compaction_trim_eval.py` starts a headless `claude -p` session with the condensing hook and the package Read rules. The session runs the extractor on fixture transcripts with planted facts. The eval reads the hook reason from the debug log and prints the share of facts that survive and the compression ratio.
- **Task tracking.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_task_tool_prompt.py -q`. The adjacent test observes a `SessionStart` context directive that names the task tool.
- **Working style.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_working_style_prompt.py -q`. The adjacent test observes the fixed context text.
- **Advisor guidance.** Input is SessionStart with `advisorModel` set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_advisor_rules_prompt.py -q`. The adjacent test observes guidance only when the advisor setting is enabled.
- **Orchestrator start.** Input is SessionStart with its opt-in flag set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_orchestrator_auto_starter.py -q`. The adjacent test observes an orchestrator directive.
- **First-task deepen.** Input is a first UserPromptSubmit task. Run `python -m pytest packages/claude-dev-env/hooks/session/test_deepen_first_prompt.py -q`. The adjacent test observes a skip table, a refusal of the paste path, a rewrite that carries the SCOPE, EXAMPLES, and ZOOM-IN BLOCKER lines, and one injection when two copies see the same Cursor prompt. `python -m pytest packages/claude-dev-env/hooks/session/test_deepen_turn_marker.py -q` observes that only the first marker claim wins. With nothing configured, `deepen_default_rewrite.py` builds that role-shaped rewrite, and `test_deepen_default_rewrite.py` checks the gate accepts it.
- **Artifact template pointer.** Input is an `Artifact` quickstart call. Run `python -m pytest packages/claude-dev-env/hooks/session/test_artifact_template_pointer.py -q`. The adjacent test observes the status flowchart path first, the html-plan path ahead of the template path in `additionalContext`, and silence on a publish call or another skill.
- **Denial quick fix.** Input is a `PermissionDenied` event with a bracketed rule label and a classifier verdict. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_auto_mode_denial_quick_fix.py -q`. The adjacent test observes the named rule, the allow entry, and the PowerShell block; a denial with no verdict gets a note and no block.

## Gotchas

- A SessionStart hook cannot run a prompt or agent hook, so the condensing step waits for the agent's Bash call. The agent hook reaches the agent only through `ok: false`, and Claude Code shows the reason as a PostToolUse hook blocking error. The Claude Code docs mark agent hooks experimental. When the agent hook fails or times out, the agent reads the printed file itself. The recall command is a plain Bash call, so a session that does not pre-approve Bash asks before it runs, and a headless `claude -p` run without Bash in `--allowedTools` denies it and keeps only the compaction summary.
- `session/skill_loaded_reminder.py` has four registration points. Its tests cover helper prompt rewriting and repeated prompt suppression.
- The advisor prompt depends on settings and an environment disable flag. The two starter scripts each use separate opt-in checks.
- The issue tracker starter requires the checkout to appear in the project path registry.
- `advisory/auto_mode_denial_quick_fix.py` lives under `advisory/` but belongs here because its only output is agent context and a one-line user message.
