---
name: deepen
description: >-
  Deepen a first user task before work starts. Triggers: /deepen, deepen this
  task, first-task deepening, Cursor Cloud launch prompt.
---

# deepen

Rewrite a user task so the worker does the omitted expert job. Keep the rewrite short.

## When this applies

- An interactive first user task on Claude Code, Cursor, or Codex
- `/deepen` with a task in the arguments
- Cursor Cloud, where user `~/.cursor/hooks.json` does not run and `sessionStart` is deferred, so the launch prompt is already sent

Skip when the prompt already carries `CDE_DEEPEN:v1`, when the text is a thanks or yes/no or status line, when it is a slash command other than `/deepen`, when it is a `/loop` or helper report, or when it is a spawn rewrite that already starts with the poteto-mode prefix.

A prompt that is only `/deepen` with no task is skipped. `/deepen` plus a task deepens the remainder.

## Four answers

1. What a top person in that field would do that this prompt omitted.
2. The raw source to start from.
3. The methods and tools they would use.
4. What besides the agent or Jon would show the result is right.

Then rewrite the user prompt to ask for exactly that job. Put `CDE_DEEPEN:v1` at the top.

## How to deepen

Read the task. Name the field. Fill the four answers from the checkout, the docs, and the tools already in the tree. Keep the rewrite shorter than a new spec. The worker should start from the raw source and finish at the proof.

When you spawn a helper to fill the four answers, that helper's prompt starts with `CDE_DEEPEN_AGENT` so the first-task hook leaves it alone.

## Hosts

- Claude desktop and CLI: a `prompt.submit` mod rewrites the visible text. The Python `UserPromptSubmit` hook is silent when that mod is on outside a cloud session.
- Claude cloud and Codex local: the Python hook injects `additionalContext`. Command hooks cannot replace the prompt string.
- Cursor Cloud: run this skill on the launch prompt.
- Codex cloud orchestration skips command hooks. Local Codex only.
