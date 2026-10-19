# Asks

**When this applies:** Every ask from the user, in every session and every host (Claude Code, Codex, Cursor).

## Rule

- Work every ask as soon as it arrives, and keep working it until it is done with proof you saw. Asks have no due dates and no deadlines. Every ask is worked now, continuously.
- Stop working an ask only when it is done with proof, or when it is blocked on something only the user can give: a decision, an approval, an account, or a credential. Put a blocked ask in front of the user in the same reply.
- "Later", "next time", "follow-up", and "parked" are not outcomes.
- Record each ask as one item in the session tracker: `TaskCreate`, `TodoWrite`, or the Codex `update_plan` tool. Mark an item completed only after you saw the proof.
- A turn ends only when every item is completed, or the reply ends with one line per item that is not:
  - `Blocked: <item> - <what the user must give>`
  - `Open: <item> - <the step you take next>`
- An `Open:` line is a report. Take its next step at once.

## Asks ledger

When the host keeps an asks ledger with `ledger.py` and `asks_check.py`, record each ask in it too:

- Record work as it happens with `ledger.py update --id <id> --progress --note "<what was done>"`. A status, owner, or note edit without `--progress` is not progress.
- Close an ask only with `ledger.py close --id <id> --proof <proof>`.
- Before you report or end a turn, run `asks_check.py --agent <your agent name> --self <your agent name>`. Act on every flagged row now, or put it in front of the user in this reply.

## Enforcement

The installer registers `open_tasks_stop_gate.py` as a Stop hook for each host:

- Claude Code: `hooks.json`. A block returns the open items as the reason, and the session keeps working.
- Codex: `$CODEX_HOME/hooks.json`. Codex turns the reason into a continuation prompt.
- Cursor: a native `stop` entry in `~/.cursor/hooks.json`. The reason comes back as `followup_message`, the next user message. A stop with status `aborted` or `error` passes, so a turn the user cancels stays silent.

The gate reads the task list from the task store, the transcript TaskCreate, TaskUpdate, and TodoWrite calls, or the Codex `update_plan` calls. It ends the hold when each open item is named on a `Blocked:` or `Open:` line of the closing reply.

## Cursor

Cursor keeps user rules in its app settings. The installer adds a native `sessionStart` entry, `cursor_agents_guidance.py`, that feeds the installed `AGENTS.md` to each Cursor session as `additional_context`.

What has been seen to work, in an interactive `cursor-agent` session (version 2026.10.16, Windows):

- The `sessionStart` entry runs, and the session can quote the Asks line. Without it, the session cannot.
- The `stop` entry runs at the end of each turn. With an open todo left, the gate sent one follow-up, and the agent closed the turn with a `Blocked:` line. Without the gate, the turn ended at "Done." with the todo still open.
- A turn cancelled with Esc sends `stop` with status `aborted`, then `error`. The gate stays silent for both.

Limits:

- `cursor-agent -p` (print mode) does not send `stop` or `beforeSubmitPrompt`, so the gate never runs there.
- The Cursor editor has not been tested.
- Cursor also runs the hooks in `~/.claude/settings.json` by default. When Claude Code hooks from this package are installed in the same home, the gate runs twice at each Cursor stop. A stop hook that comes from that file has no follow-up limit in Cursor, so the gate passes once `loop_count` reaches 5.
- One entry in the Claude Code format inside `~/.cursor/hooks.json` makes Cursor skip every hook in that file. The installer writes only native entries and converts older ones.
