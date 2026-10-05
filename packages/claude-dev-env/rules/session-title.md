# Status in the session title

**When:** The session has a tool whose name ends in `__set_session_title`.

Before each turn ends, set the title to `<emoji> <name>`. Use the red flag when the user must act, the check mark when the work is done, and the hourglass while work, CI, or a merge queue runs. The name has 25 characters or fewer, in sentence case, with concrete nouns and no IDs, dates, or branch names. Set it before the final reply and never mention it to the user.

**Enforcement:** `hooks/blocking/session_title_format_gate.py` denies a malformed title; `hooks/blocking/session_title_stop_gate.py` blocks a turn end with no title.

**Full text:** [`docs/rule-guides/session-title.md`](../docs/rule-guides/session-title.md). Read it for the emoji table and naming rules.
