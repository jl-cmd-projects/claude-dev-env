# Session context

This family injects reminders and task guidance when an agent starts, resumes, submits a prompt, spawns a helper, or hits an auto mode denial. The startup scripts leave the session quiet when their opt-in conditions fail.

## Checks

- `session/skill_loaded_reminder.py` injects a poteto-mode reminder when the skill needs loading or reloading.
- `session/task_tool_prompt.py` injects a task tracking directive at session start.
- `session/working_style_prompt.py` injects the session's working style at session start.
- `session/advisor_rules_prompt.py` injects advisor guidance when the built-in advisor is enabled.
- `session/orchestrator_auto_starter.py` injects an orchestrator directive when its environment flag is enabled.
- `session/issue_tracker_session_starter.py` injects issue tracker guidance when enabled for a registered repository.
- `advisory/auto_mode_denial_quick_fix.py` proposes one `autoMode.allow` entry and a PowerShell block that writes it after an auto mode denial. It never retries the denied call.

## When it fires

- `session/skill_loaded_reminder.py` runs on `PreToolUse` matcher `Agent|Task` at `10` seconds, `UserPromptSubmit` matcher empty at `10` seconds, `SessionStart` matcher `compact` at `10` seconds, and `SubagentStart` matcher `workflow-subagent` at `10` seconds in `hooks.json`.
- `session/task_tool_prompt.py`, `session/working_style_prompt.py`, `session/advisor_rules_prompt.py`, `session/orchestrator_auto_starter.py`, and `session/issue_tracker_session_starter.py` run on `SessionStart`, matcher empty, timeout `10` seconds each in `hooks.json`.
- `advisory/auto_mode_denial_quick_fix.py` runs on `PermissionDenied`, matcher `*`, timeout `10` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. Enable opt-in flags only inside the tests.

- **Skill reminder.** Input is a helper spawn whose prompt lacks poteto-mode. Run `python -m pytest packages/claude-dev-env/hooks/session/test_skill_loaded_reminder.py -q`. The adjacent test observes the reminder and leaves an already prepared prompt unchanged.
- **Task tracking.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_task_tool_prompt.py -q`. The adjacent test observes a `SessionStart` context directive that names the task tool.
- **Working style.** Input is a SessionStart event. Run `python -m pytest packages/claude-dev-env/hooks/session/test_working_style_prompt.py -q`. The adjacent test observes the fixed context text.
- **Advisor guidance.** Input is SessionStart with `advisorModel` set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_advisor_rules_prompt.py -q`. The adjacent test observes guidance only when the advisor setting is enabled.
- **Orchestrator start.** Input is SessionStart with its opt-in flag set. Run `python -m pytest packages/claude-dev-env/hooks/session/test_orchestrator_auto_starter.py -q`. The adjacent test observes an orchestrator directive.
- **Issue tracker start.** Input is SessionStart with its opt-in flag and a registered checkout. Run `python -m pytest packages/claude-dev-env/hooks/session/test_issue_tracker_session_starter.py -q`. The adjacent test observes issue tracker context.
- **Denial quick fix.** Input is a `PermissionDenied` event with a bracketed rule label and a classifier verdict. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_auto_mode_denial_quick_fix.py -q`. The adjacent test observes the named rule, the allow entry, and the PowerShell block; a denial with no verdict gets a note and no block.

## Gotchas

- `session/skill_loaded_reminder.py` has four registration points. Its tests cover helper prompt rewriting and repeated prompt suppression.
- The advisor prompt depends on settings and an environment disable flag. The two starter scripts each use separate opt-in checks.
- The issue tracker starter requires the checkout to appear in the project path registry.
- `advisory/auto_mode_denial_quick_fix.py` lives under `advisory/` but belongs here because its only output is agent context and a one-line user message.
