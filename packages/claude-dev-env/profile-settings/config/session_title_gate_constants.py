"""Constants for the session-title Stop hook gate."""

ALL_TITLE_TOOL_NAMES = frozenset(
    {
        "mcp__claude-code-remote__set_session_title",
        "mcp__ccd_session_mgmt__set_session_title",
    }
)
INSTRUCTION = (
    "Call set_session_title (session id from get_session) before you stop. "
    'Title = "<emoji> <brief task name>", one line in a narrow sidebar. '
    "\U0001f6a9 = Jon must act (question, approval, a step only he can do). "
    "✅ = fully done (merged or nothing left). "
    "⏳ = work, CI, or a merge queue still running and nothing waits on Jon."
)
