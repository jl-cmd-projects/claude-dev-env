# deepen-first-prompt

A Claude Code mod on `prompt.submit`. It rewrites the first interactive user task so the worker does the omitted expert job. The transcript and the prompt history show the new text.

## What it does

- On a submitted prompt, it runs the claude-dev-env gate `hooks/session/deepen_first_prompt.py` under `CLAUDE_CONFIG_DIR`, or under `~/.claude` when that variable is unset.
- It sends the gate a `UserPromptSubmit` payload with the prompt and the session id, and sets `CDE_DEEPEN_OUTPUT=rewrite`.
- When the gate prints a task that opens with `CDE_DEEPEN:v1`, that task replaces the submitted text.
- When the gate prints nothing, the prompt goes through unchanged. The gate skips a thanks, a slash command, a `/loop`, a spawn rewrite, a later turn, and `CDE_SKIP_DEEPEN=1`.
- A session that already holds a user message goes through unchanged, and the gate does not run.
- It tries `python3`, then `python`. Each run stops after 8 seconds. When no launcher answers, the prompt goes through unchanged.

## Hosts

This plugin is for Claude desktop and the Claude CLI. The claude-dev-env installer adds it on a full install. Set `--no-deepen-first-prompt` or `CDE_INSTALL_DEEPEN_FIRST_PROMPT=0` to leave it out.

The Python `UserPromptSubmit` hook in claude-dev-env stays silent while this plugin is on outside a cloud session. In a cloud session, and in Codex, that hook injects the deepened task as `additionalContext`.

## Test

```sh
claude plugin validate .
claude plugin test .
```
