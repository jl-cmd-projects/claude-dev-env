Back to the [rules index](../../rules/index.md).

# Status in the session title

## In brief

Before each turn ends, set the title to `<emoji> <name>`. Use the red flag when the user must act, the check mark when the work is done, and the hourglass while work, CI, or a merge queue runs. The name has 25 characters or fewer, in sentence case, with concrete nouns and no IDs, dates, or branch names.

**Enforcement:** `hooks/blocking/session_title_format_gate.py` denies a malformed title.

**When this applies:** The session has a tool whose name ends in `__set_session_title`, such as `mcp__claude-code-remote__set_session_title` in a cloud session or `mcp__ccd_session_mgmt__set_session_title` in the desktop app.

## Rule

Before each turn ends, set the title to `<emoji> <name>`. Get the session id from `get_session` with no `session_id` when the tool asks for one.

Set the title before the final reply, and set it in silence. The reply to the user carries no mention of the title, its emoji, or the reminder that asked for it.

## Status emoji

| Emoji | Use it when |
|---|---|
| Red flag | The user must act: a question, an approval, or a step only the user can do. |
| Check mark | The work is done: merged, or nothing left. |
| Hourglass | Work, CI, or a merge queue still runs and nothing waits on the user. |

## Name

The name has 25 characters or fewer and names the main change or outcome in concrete nouns, such as `Broker gate + replay rule`. Join two parts with ` + `. Use sentence case and no end punctuation. Leave out dates, IDs, branch names, and filler words such as "work on" or "fix for". Rename the session when the scope of the work changes.

## Enforcement

`hooks/blocking/session_title_format_gate.py` denies a malformed title.
