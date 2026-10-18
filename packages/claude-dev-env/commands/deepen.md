---
description: Deepen a task into the standing job before work starts
argument-hint: [task to deepen]
---

Deepen this task before any work starts: `$ARGUMENTS`

When `$ARGUMENTS` is empty, ask the user to paste the task and stop.

When `$ARGUMENTS` holds a task, follow DeepStack intake at https://github.com/jl-cmd-projects/DeepStack/blob/main/plugins/deepstack/skills/deepstack-mode/references/intake.md.

Write `SCOPE (role):`, `EXAMPLES (illustration only):`, and `ZOOM-IN BLOCKER:` before any plan. Put `CDE_DEEPEN:v1` on line 1 of the worker prompt and carry the scope line there. The deepening pass writes that prompt and stops.

Skip this command when the prompt already carries `CDE_DEEPEN:v1`.
