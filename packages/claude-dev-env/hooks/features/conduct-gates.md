# Conduct gates

This family stops a chat reply, edited message, or tool call when its payload breaks a session rule. Each gate gives the agent a reason it can act on.

## Checks

- `blocking/reply_length_gate.py` caps chat reply length, denies a configured banned word, requires a readable link when the text names a pull request number, and denies a causal claim in a reply that cites no code span, output block, or link. With visual reply mode on, it also runs the checks in `visual_reply_rules.py` from the rule list in `rules/visual-reply-rules.json`: no abbreviation or tracker number outside a link, a widget or page before a reply of more than one sentence, and no anchor link inside widget code. The mode is off by default; `~/.claude/visual-reply-mode.json` with `{"enabled": true}` turns the mode checks on.
- `blocking/edit_marker_gate.py` rejects strikethrough and edit-note markers in replacement chat text or cards.
- `blocking/issue_close_handoff_gate.py` denies an issue comment or issue write that closes the issue and routes a found defect to another issue or epic.
- `blocking/session_title_format_gate.py` denies a session title that breaks the `<emoji> <name>` shape or has a name longer than 25 characters.
- `blocking/step_note_gate.py` requires a status line before a tool call while its opt-in flag is on.
- `blocking/verify_before_acting.py` blocks a completed mutating call when the agent's reasoning contains an unchecked claim.
- `blocking/pr_lifecycle_skill_gate.py` denies a commit, push, pull request action, or merge until the `pr-lifecycle` skill appears in the transcript since the last compaction.
- `blocking/artifact_dark_mode_gate.py` denies an Artifact page publish when the page, inside the publish wrapper, keeps a light body or shows text under 4.5:1 contrast in dark mode. `blocking/artifact_dark_mode_render.cjs` renders the page in headless Chromium for it.

## When it fires

- `blocking/reply_length_gate.py` runs on `PreToolUse`, matcher `mcp__hearthbot__reply|mcp__hearthbot__post_message|mcp__hearthbot__ask_decision|mcp__hearthbot__post_widget`, timeout `10` seconds in `hooks.json`.
- `blocking/edit_marker_gate.py` runs on `PreToolUse`, matcher `mcp__.*__update_message`, timeout `10` seconds in `hooks.json`.
- `blocking/issue_close_handoff_gate.py` runs on `PreToolUse`, matcher `mcp__.*__(add_issue_comment|issue_write|update_issue_comment)`, timeout `10` seconds in `hooks.json`.
- `blocking/session_title_format_gate.py` runs on `PreToolUse`, matcher `mcp__.*__set_session_title`, timeout `10` seconds in `hooks.json`.
- `blocking/step_note_gate.py` runs on `PreToolUse`, matcher `*`, timeout `15` seconds in `hooks.json`.
- `blocking/verify_before_acting.py` runs on `PostToolUse`, matcher `Write|Edit|MultiEdit|NotebookEdit|Agent|Task|apply_patch|Bash|PowerShell|mcp__.*`, timeout `10` seconds in `hooks.json`.
- `blocking/pr_lifecycle_skill_gate.py` runs on `PreToolUse`, matcher `Bash|PowerShell|mcp__.*__(create_pull_request|merge_pull_request|enable_pr_auto_merge|update_pull_request|actions_run_trigger)`, timeout `10` seconds in `hooks.json`.
- `blocking/artifact_dark_mode_gate.py` runs on `PreToolUse`, matcher `Artifact`, timeout `60` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests create transcript and payload fixtures.

- **Reply length.** Input is a reply with four sentences, a plain pull request number, an abbreviation, two sentences with no widget this turn, or widget code with an anchor link. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_reply_length_gate.py -q`. The adjacent test observes a denial and its count, link, or mode reason.
- **Edit marker.** Input is an update message with strikethrough or an edit note. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_edit_marker_gate.py -q`. The adjacent test observes a denial; clean replacement text passes.
- **Handoff close.** Input is an issue comment that says the issue is closed and that the found defect belongs to another issue. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_issue_close_handoff_gate.py -q`. The adjacent test observes a denial; a close with a plain cross-reference and a routing comment on an open issue both pass.
- **Session title.** Input is a set session title call with no leading emoji or a name over 25 characters. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_session_title_format_gate.py -q`. The adjacent test observes a denial that names the broken rule; a well-formed title passes.
- **Step note.** Input is a tool call after a transcript message without a status line while the flag is on. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_step_note_gate.py -q`. The adjacent test observes a block until a status line appears.
- **Checked claim.** Input is a Write after hedged reasoning in the transcript. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_verify_before_acting.py -q`. The adjacent test observes a block and a logged blocked outcome.
- **Lifecycle skill.** Input is a `git commit` or `gh pr create` command with no `pr-lifecycle` invocation in the transcript. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_pr_lifecycle_skill_gate.py -q`. The adjacent test observes a denial, then a silent allow once the skill or its slash command appears.
- **Dark mode page.** Input is an Artifact publish of a page that themes `html` but leaves `body` to the publish wrapper. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_artifact_dark_mode_gate.py -q`. The adjacent test observes a denial that names the text and its contrast; a page that themes `body` passes. The render tests skip on a host with no Node Playwright and Chromium.

## Gotchas

- `blocking/step_note_gate.py` is off by default and polls for the transcript record. Subagent calls and unreadable records pass.
- `blocking/verify_before_acting.py` runs after the tool. A block asks the agent to check the claim and undo a contradicted change.
- The reply gate counts each nonempty list line as a sentence. Link targets and code spans add no words. Its banned words come from `reply-banned-words.json` in the Claude home, or the file `CLAUDE_REPLY_BANNED_WORDS_PATH` names, with built-in defaults.
- The edit marker gate scans replacement cards as well as the message text.
- The handoff close gate reads the `body` and `comment` fields of issue tools only. A `gh issue close --comment` command in Bash and a pull request body that closes the issue with `Closes #N` do not reach it.
- The lifecycle gate counts only invocations after the last compaction, so a compacted session invokes `pr-lifecycle` again. A missing or unreadable transcript allows the call.
- The dark mode gate denies a page publish when Node, Playwright or Chromium is missing, and its reason names the install command. It checks both dark signals, `prefers-color-scheme: dark` and `data-theme="dark"` on the root element.
