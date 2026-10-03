# Conduct gates

This family stops a chat reply, edited message, or tool call when its payload breaks a session rule. Each gate gives the agent a reason it can act on.

## Checks

- `blocking/reply_length_gate.py` caps chat reply length and requires a readable link when the text names a pull request number.
- `blocking/edit_marker_gate.py` rejects strikethrough and edit-note markers in replacement chat text or cards.
- `blocking/step_note_gate.py` requires a status line before a tool call while its opt-in flag is on.
- `blocking/verify_before_acting.py` blocks a completed mutating call when the agent's reasoning contains an unchecked claim.

## When it fires

- `blocking/reply_length_gate.py` runs on `PreToolUse`, matcher `mcp__hearthbot__reply|mcp__hearthbot__post_message`, timeout `10` seconds in `hooks.json`.
- `blocking/edit_marker_gate.py` runs on `PreToolUse`, matcher `mcp__.*__update_message`, timeout `10` seconds in `hooks.json`.
- `blocking/step_note_gate.py` runs on `PreToolUse`, matcher `*`, timeout `15` seconds in `hooks.json`.
- `blocking/verify_before_acting.py` runs on `PostToolUse`, matcher `Write|Edit|MultiEdit|NotebookEdit|Agent|Task|apply_patch|Bash|PowerShell|mcp__.*`, timeout `10` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests create transcript and payload fixtures.

- **Reply length.** Input is a reply with four sentences or a plain pull request number. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_reply_length_gate.py -q`. The adjacent test observes a denial and its count or link reason.
- **Edit marker.** Input is an update message with strikethrough or an edit note. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_edit_marker_gate.py -q`. The adjacent test observes a denial; clean replacement text passes.
- **Step note.** Input is a tool call after a transcript message without a status line while the flag is on. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_step_note_gate.py -q`. The adjacent test observes a block until a status line appears.
- **Checked claim.** Input is a Write after hedged reasoning in the transcript. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_verify_before_acting.py -q`. The adjacent test observes a block and a logged blocked outcome.

## Gotchas

- `blocking/step_note_gate.py` is off by default and polls for the transcript record. Subagent calls and unreadable records pass.
- `blocking/verify_before_acting.py` runs after the tool. A block asks the agent to check the claim and undo a contradicted change.
- The reply gate counts each nonempty list line as a sentence. Link targets and code spans add no words.
- The edit marker gate scans replacement cards as well as the message text.
