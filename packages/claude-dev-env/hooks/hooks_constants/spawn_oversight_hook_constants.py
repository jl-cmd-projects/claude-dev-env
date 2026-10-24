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
    "You own the work this spawn starts. Run each piece through the verified-work "
    "flow: research, then a separate verifier checks the research; plan, then a "
    "separate verifier checks that the plan fixes the researched issue; implement, "
    "then a separate verifier reproduces the issue on the old state before it "
    "confirms the fix on the new state. Spawn a fresh verifier agent for each "
    "check, never the agent that did the work, and brief it with the issue and "
    "the sources and leave the worker's conclusion out. A verifier's check ends "
    "the chain and gets no verifier of its own. Ask the user once before "
    "you build new scope the user's words do not name, and keep in-scope work "
    "moving while the question waits. Report as done only what a verifier "
    "passed, with its evidence. While the agent runs, read its progress and wake "
    "it with one next step when it goes quiet. Load the orchestrator skill and "
    "follow its oversee delegated work reference."
)
