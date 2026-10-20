"""Constants for the spawn oversight PreToolUse hook.

Groups: the payload keys it reads, the brief markers it requires, the
refusal it gives a brief without them, and the oversight directive it adds to
every spawn that passes.
"""

from __future__ import annotations

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
DENY_DECISION = "deny"
WORKFLOW_TOOL_NAME = "Workflow"

ALL_OUTCOME_MARKERS = ("outcome:",)
ALL_BLOCKER_CLAUSE_MARKERS = ("on a blocker:", "at a blocker:")
MARKER_DECORATION_CHARACTERS = "*_` \t"

MISSING_OUTCOME_REASON = (
    "The brief has no outcome line. Add `Outcome: <what the user has when the "
    "work is done>`."
)
MISSING_BLOCKER_CLAUSE_REASON = (
    "The brief has no blocker clause. Add `On a blocker: try other routes that "
    "reach the outcome; hand the user a step only when it needs their hands.` "
    "Name any route as `Suggested route: <route>`, a default the worker may leave."
)
REFUSAL_PREFIX = "Spawn refused before the worker starts."
REFUSAL_SUFFIX = (
    "The worker owns reaching the outcome by any allowed route. Add the "
    "missing lines and call the spawn again."
)
REASON_SEPARATOR = " "

SPAWN_OVERSIGHT_DIRECTIVE = (
    "You own the work this spawn starts. Load the orchestrator skill and follow "
    "its oversee delegated work reference. While the agent runs, read its progress "
    "and wake it with one next step when it goes quiet. Before its output "
    "reaches the user, check it against the user's own words and standards, and "
    "send the agent a correction when it misses. Give each piece of a "
    "multi-piece task its own reviewer or helper. Tell the user you are "
    "checking the work."
)
