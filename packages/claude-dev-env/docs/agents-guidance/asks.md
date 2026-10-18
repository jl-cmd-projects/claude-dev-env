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
- Cursor: `~/.cursor/hooks.json`. The reason comes back as `followup_message`, the next user message.

The gate reads the task list from the task store, the transcript TaskCreate, TaskUpdate, and TodoWrite calls, or the Codex `update_plan` calls. It ends the hold when each open item is named on a `Blocked:` or `Open:` line of the closing reply.

Cursor keeps user rules in its app settings. The installer adds a Cursor SessionStart hook, `cursor_agents_guidance.py`, that feeds the installed `AGENTS.md` to each Cursor session.
