Back to the [rules index](../../rules/index.md).

# Status in the session title

## In brief

Keep the title's status current: set `<emoji> <name>` when the status changes, and set the hourglass when a new ask starts work. Use the red flag when the user must act, the construction sign when an outside dependency blocks the work, the check mark when the work is done, and the hourglass while work, CI, or a merge queue runs. The name has 25 characters or fewer, in sentence case, with concrete nouns and no IDs, dates, or branch names.

**Enforcement:** `hooks/blocking/session_title_format_gate.py` denies a malformed title. `hooks/blocking/session_title_turn_gate.py` holds a turn once when the title shows a stale status.

**When this applies:** The session has a tool whose name ends in `__set_session_title`, such as `mcp__claude-code-remote__set_session_title` in a cloud session or `mcp__ccd_session_mgmt__set_session_title` in the desktop app.

## Rule

Set the title to `<emoji> <name>` when the session's status changes, at any point in a turn. A title that still fits needs no new call. When a new ask arrives while the title shows the red flag or the check mark, set the hourglass before other work, so the user sees the session working. Get the session id from `get_session` with no `session_id` when the tool asks for one.

Set the title before the final reply, and set it in silence. The reply to the user carries no mention of the title, its emoji, or the reminder that asked for it. When the Stop gate holds the turn after the answer went out, call the title tool and close with one short sentence. Leave the answer as it stands.

## Status emoji

| Emoji | Use it when |
|---|---|
| Red flag | The user must act: a question, an approval, or a step only the user can do. |
| Construction sign | An outside dependency blocks the work and the user cannot clear it right now, such as a refused push or an unreachable host. |
| Check mark | The work is done: merged, or nothing left. |
| Hourglass | Work, CI, or a merge queue still runs and nothing waits on the user. |

## Name

The name has 25 characters or fewer and names the main change or outcome in concrete nouns, such as `Broker gate + replay rule`. Join two parts with ` + `. Use sentence case and no end punctuation. Leave out dates, IDs, branch names, and filler words such as "work on" or "fix for". Rename the session when the scope of the work changes.

## Enforcement

`hooks/blocking/session_title_format_gate.py` denies a malformed title.

`hooks/blocking/session_title_turn_gate.py` is a Stop hook. It holds the end of a turn once when the shown title does not fit the session's state:

- No title is set yet.
- The red flag shows, and the prompt that started the turn asks for work.
- The check mark shows, and the task list has open items.
- The hourglass shows, and every task list item is completed or deleted.

A turn that set a title passes, because the agent's choice stands. A turn that called no tool other than the title tool passes, and so does a held turn. It applies when the transcript shows the title tool.

`hooks/session/tracking_nudge.py` runs when the user sends a prompt. When the prompt asks for work and the title shows the red flag or the check mark, it adds a note that asks for the hourglass before other work. The note never blocks.
