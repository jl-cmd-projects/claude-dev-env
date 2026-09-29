"""Constants for the thread spawn pace PreToolUse hook.

Groups: the usage-pace script it runs, the reshape values for an over-pace
spawn, and the hook output keys and messages.
"""

from __future__ import annotations

USAGE_PACE_SCRIPT_ENV_VAR = "COORDINATOR_USAGE_PACE_SCRIPT"
USAGE_PACE_SCRIPT_FILE_NAME = "usage_pace.py"
USAGE_PACE_TIMEOUT_SECONDS = 15

TOOL_INPUT_KEY = "tool_input"
THREAD_MODEL_WHEN_OVER_PACE = "claude-sonnet-5-5"
THREAD_EFFORT_WHEN_OVER_PACE = "medium"
MODEL_INPUT_KEY = "model"
EFFORT_INPUT_KEY = "effort"
INSTRUCTIONS_INPUT_KEY = "instructions"
INSTRUCTIONS_MAXIMUM_BYTES = 8192
INSTRUCTIONS_SEPARATOR = "\n\n"
INSTRUCTIONS_ENCODING = "utf-8"
FABLE_ADVISOR_LINE = (
    "Mandatory Fable advisor: usage is over pace, so this thread runs on "
    "Sonnet 5.5 at medium effort. Before substantive work and again before "
    "you report done, consult an Agent subagent with model fable as your "
    "advisor, and name its verdict in your report."
)

PERMISSION_DENY = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
NOT_AN_OBJECT_REASON = "start_thread_session input is not a JSON object"
NO_INSTRUCTIONS_REASON = "start_thread_session input has no instructions text"
OVER_BYTE_CAP_REASON_TEMPLATE = (
    "usage is over pace and the brief plus the mandatory Fable advisor line is "
    "{reshaped_byte_count} bytes, over the {maximum_bytes}-byte cap; "
    "shorten the instructions by {excess_byte_count} bytes"
)
RESHAPE_CONTEXT_PREFIX = (
    "Usage over pace or unreadable: this thread spawn now runs on "
    "claude-sonnet-5-5 at medium effort with a mandatory Fable advisor line. "
    "Pace verdict: "
)
PACE_VERDICT_CONTEXT_MAXIMUM_CHARACTERS = 600
LAUNCH_FAILURE_ERROR_TEMPLATE = "usage pace did not finish: {failure_type}"
