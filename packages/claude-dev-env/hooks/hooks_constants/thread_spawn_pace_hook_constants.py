"""Constants for the thread spawn pace PreToolUse hook.

Groups: the usage-pace script it runs, the reshape values for an over-pace
spawn, and the hook output keys and messages.
"""

from __future__ import annotations

USAGE_PACE_SCRIPT_ENV_VAR = "COORDINATOR_USAGE_PACE_SCRIPT"
USAGE_PACE_SCRIPT_FILE_NAME = "usage_pace.py"
USAGE_PACE_TIMEOUT_SECONDS = 15

TOOL_INPUT_KEY = "tool_input"
THREAD_MODEL_WHEN_OVER_PACE = "opus"
THREAD_EFFORT_WHEN_OVER_PACE = "low"
MODEL_INPUT_KEY = "model"
EFFORT_INPUT_KEY = "effort"

PERMISSION_DENY = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
NOT_AN_OBJECT_REASON = "start_thread_session input is not a JSON object"
RESHAPE_CONTEXT_PREFIX = (
    "Usage over pace or unreadable: this thread spawn now runs on "
    "opus at low effort. Pace verdict: "
)
PACE_VERDICT_CONTEXT_MAXIMUM_CHARACTERS = 600
LAUNCH_FAILURE_ERROR_TEMPLATE = "usage pace did not finish: {failure_type}"
