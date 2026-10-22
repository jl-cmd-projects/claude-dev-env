# Asks

**When this applies:** Every ask from the user, in every session and every host (Claude Code, Codex, Cursor).

## Rule

- Work every ask as soon as it arrives, and keep working it until it is done with proof you saw. Asks have no due dates and no deadlines. Every ask is worked now, continuously.
- Stop working an ask only when it is done with proof, or when it is blocked on something only the user can give: a decision, an approval, an account, or a credential. Put a blocked ask in front of the user in the same reply.
- "Later", "next time", "follow-up", and "parked" are not outcomes.
- Record each ask as one item in the session tracker: `TaskCreate`, `TodoWrite`, or the Codex `update_plan` tool. The user follows your work there.
- Keep each item's status current as the work moves: in progress when you start it, completed only after you saw the proof. A long turn updates the list at each step, so the list never lags the work.
- An item blocked on the user stays open, and the reply says what the user must give.

## Asks ledger

When the host keeps an asks ledger with `ledger.py` and `asks_check.py`, record each ask in it too:

- Record work as it happens with `ledger.py update --id <id> --progress --note "<what was done>"`. A status, owner, or note edit without `--progress` is not progress.
- Close an ask only with `ledger.py close --id <id> --proof <proof>`.
- Before you report or end a turn, run `asks_check.py --agent <your agent name> --self <your agent name>`. Act on every flagged row now, or put it in front of the user in this reply.

## Enforcement

The installer registers `open_tasks_stop_gate.py` as a Stop hook for each host:

- Claude Code: `hooks.json`. A block returns the reason, and the session updates its task list and ends the turn. An install into `~/.claude` also adds the same Stop entry to every profile under `~/.claude-profiles` that has its own `settings.json` and does not already run its own copy of the gate. A profile whose `settings.json` links to `~/.claude/settings.json` already has it. Uninstall removes only that entry. On install, a profile `settings.json` that is not valid JSON is left unchanged and listed under Action needed with its path and parse error, and the rest of the install goes on. On uninstall, such a file that still names the gate stops the uninstall before anything changes, so the manifest stays and a rerun after the fix removes the gate; one that does not name the gate is left as it is.
- Codex: `$CODEX_HOME/hooks.json`. Codex turns the reason into a continuation prompt.
- Cursor: a native `stop` entry in `~/.cursor/hooks.json`. The reason comes back as `followup_message`, the next user message. A stop with status `aborted` or `error` passes, so a turn the user cancels stays silent.

The gate holds a turn once when all three hold:

- The prompt that started the turn asks for work. A question, an acknowledgement such as `thanks!`, and an envelope such as `<task-notification>` do not.
- The turn ran a work tool: any tool but a tracker call, the session title tool, `AskUserQuestion`, Codex `request_user_input`, `ToolSearch`, `TaskList`, or `TaskGet`. A turn that only asks the user a question passes.
- The turn made no tracker call: TaskCreate, TaskUpdate, TodoWrite, the Codex `update_plan`, or the Claude Code desktop `mcp__ccd_turn__update_plan`.

The gate never reads the reply text. A held turn passes, so the gate adds at most one step to a turn.

In Claude Code, `tracking_nudge.py` runs on `UserPromptSubmit`. For a prompt that asks for work, it adds one note that asks for a task list item, so the agent tracks the ask before it starts. The note never blocks.

## Cursor

Cursor keeps user rules in its app settings. The installer adds a native `sessionStart` entry, `cursor_agents_guidance.py`, that feeds the installed `AGENTS.md` to each Cursor session as `additional_context`.

What has been seen to work, in an interactive `cursor-agent` session (version 2026.10.16, Windows):

- The `sessionStart` entry runs, and the session can quote the Asks line. Without it, the session cannot.
- The `stop` entry runs at the end of each turn. This test ran on the earlier version of the gate, which read `Blocked:` lines in the reply. With an open todo left, the gate sent one follow-up, and the agent closed the turn with a `Blocked:` line. Without the gate, the turn ended at "Done." with the todo still open.
- A turn cancelled with Esc sends `stop` with status `aborted`, then `error`. The gate stays silent for both.
- On Windows, each hook command runs in PowerShell: Cursor writes it into a temporary `.ps1` script and starts `pwsh -NonInteractive -File` on it. A command that starts with a quote gets the `&` call operator first, so a quoted Python path with a space runs. A probe from `C:/.../py space/venv/Scripts/python.exe` ran with both a bare and a quoted script path. The Cursor editor (3.24.12) has the same `&` rule in its hook runner.

Limits:

- `cursor-agent -p` (print mode) does not send `stop` or `beforeSubmitPrompt`, so the gate never runs there.
- The Cursor editor has not been tested.
- Cursor also runs the hooks in `~/.claude/settings.json` by default. When Claude Code hooks from this package are installed in the same home, the gate runs twice at each Cursor stop. A stop hook that comes from that file has no follow-up limit in Cursor, so the gate passes any stop whose `loop_count` is above 0.
- One entry in the Claude Code format inside `~/.cursor/hooks.json` makes Cursor skip every hook in that file. The installer writes only native entries and converts older ones.
