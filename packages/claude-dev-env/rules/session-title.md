# Status in the session title

**When:** The session has a tool whose name ends in `__set_session_title`, such as `mcp__claude-code-remote__set_session_title` in a cloud session or `mcp__ccd_session_mgmt__set_session_title` in the desktop app.

Before each turn ends, set the title to `<emoji> <name>`. Get the session id from `get_session` with no `session_id` when the tool asks for one.

- Use the red flag emoji when the user must act: a question, an approval, or a step only the user can do.
- Use the check mark emoji when the work is done: merged, or nothing left.
- Use the hourglass emoji while work, CI, or a merge queue still runs and nothing waits on the user.

The name has 25 characters or fewer and names the main change or outcome in concrete nouns, such as `Broker gate + replay rule`. Join two parts with ` + `. Use sentence case and no end punctuation. Leave out dates, IDs, branch names, and filler words such as "work on" or "fix for". Rename the session when the scope of the work changes.

**Enforcement:** `hooks/blocking/session_title_format_gate.py` denies a malformed title. `hooks/blocking/session_title_stop_gate.py` blocks the end of a turn that set no title.
