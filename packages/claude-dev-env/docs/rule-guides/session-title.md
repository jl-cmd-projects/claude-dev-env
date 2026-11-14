Back to the [rules index](../../rules/index.md).

# Status in the session title

## In brief

Keep the title's status current. Set `<emoji> <name>` when the status changes. Set the hourglass when a new ask starts work. Use the red flag when the user must act, the construction sign when an outside dependency blocks the work, the check mark when the work is done, and the hourglass while work, CI, or a merge queue runs. The name has 25 characters or fewer, in sentence case, with concrete nouns and no IDs, dates, or branch names.

**Enforcement:** `hooks/blocking/session_title_format_gate.py` denies a malformed title. `hooks/session/tracking_nudge.py` adds a quiet note to a new ask when the title is missing or stale.

**When this applies:** The session has a tool whose name ends in `__set_session_title`, such as `mcp__claude-code-remote__set_session_title` in a cloud session or `mcp__ccd_session_mgmt__set_session_title` in the desktop app.

## Rule

Set the title to `<emoji> <name>` when the session's status changes, at any point in a turn. A title that still fits needs no new call. When a new ask arrives while the title shows the red flag or the check mark, set the hourglass before other work, so the user sees the session working. Get the session id from `get_session` with no `session_id` when the tool asks for one.

Set the title before the final reply, and set it in silence. The reply to the user carries no mention of the title, its emoji, or the reminder that asked for it.

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

No hook holds the end of a turn for the title.

`hooks/session/tracking_nudge.py` runs when the user sends a prompt. It adds a quiet note when the prompt asks for work:

- The title shows the red flag or the check mark. The note names that title and asks for the hourglass before other work.
- The session has no title yet. The note names the title tool and asks for `⏳ <name>` before other work. It shows at most once in a session, compactions included.
- The title shows the hourglass or the construction sign. No note.

The note never blocks. It applies when the transcript shows the title tool. A cloud session lists the tool only partway through its first turn, so the no title note can come on the second ask.
