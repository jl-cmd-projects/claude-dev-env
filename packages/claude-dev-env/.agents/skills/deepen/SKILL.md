---
name: deepen
description: >-
  Deepen a first user task before work starts. Triggers: /deepen, deepen this
  task, first-task deepening, Cursor Cloud launch prompt. DeepStack intake
  holds the contract.
---

# deepen

On a first task, `/deepen` plus a task, or a routine wake that has work, read DeepStack intake and follow it: [intake](https://github.com/jl-cmd-projects/DeepStack/blob/main/plugins/deepstack/skills/deepstack-mode/references/intake.md).

Skip when the prompt already carries `CDE_DEEPEN:v1`, when the text is a thanks or yes/no or status line, when it is a slash command other than `/deepen`, when it is a `/loop` or helper report, or when it is a spawn rewrite that already starts with the poteto-mode prefix.

A prompt that is only `/deepen` with no task is skipped. `/deepen` plus a task deepens the remainder.

The deepening pass writes the worker prompt and stops. The worker runs that prompt.

When you spawn a helper to fill the four answers, that helper's prompt starts with `CDE_DEEPEN_AGENT` so the first-task hook leaves it alone.

## Hosts

- Claude desktop and CLI: a `prompt.submit` mod rewrites the visible text. The Python `UserPromptSubmit` hook is silent when that mod is on outside a cloud session.
- Claude cloud and Codex local: the Python hook injects `additionalContext`. Command hooks cannot replace the prompt string.
- Cursor Cloud: run DeepStack intake on the launch prompt. The host adapter for the three lines and the refusal lives with that host. This package keeps the gate.
- Codex cloud orchestration skips command hooks. Local Codex only.
