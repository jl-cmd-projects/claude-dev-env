"""Constants for the subagent effort route.

Groups: the allowed effort for each Anthropic model family, the effort a spawn
gets when it names none or names one outside its family's list, the tool
input keys, and the hook output text.
"""

from __future__ import annotations

OPUS_MODEL_FAMILY = "opus"
SONNET_MODEL_FAMILY = "sonnet"
FABLE_MODEL_FAMILY = "fable"
HAIKU_MODEL_FAMILY = "haiku"

ALL_ALLOWED_EFFORTS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    OPUS_MODEL_FAMILY: ("medium",),
    SONNET_MODEL_FAMILY: ("high",),
    FABLE_MODEL_FAMILY: ("low", "medium", "high"),
    HAIKU_MODEL_FAMILY: ("low", "medium", "high", "xhigh", "max"),
}

ALL_ROUTED_EFFORT_BY_FAMILY: dict[str, str] = {
    OPUS_MODEL_FAMILY: "medium",
    SONNET_MODEL_FAMILY: "high",
    FABLE_MODEL_FAMILY: "high",
    HAIKU_MODEL_FAMILY: "medium",
}

MODEL_INPUT_KEY = "model"
EFFORT_INPUT_KEY = "effort"
SUBAGENT_TYPE_INPUT_KEY = "subagent_type"
FORK_SUBAGENT_TYPE = "fork"

TOOL_INPUT_KEY = "tool_input"
TRANSCRIPT_PATH_KEY = "transcript_path"
TRANSCRIPT_ENTRY_TYPE_KEY = "type"
TRANSCRIPT_ASSISTANT_TYPE = "assistant"
TRANSCRIPT_MESSAGE_KEY = "message"
TRANSCRIPT_TAIL_BYTES = 2_000_000
SEEK_FROM_FILE_END = 2

ADDITIONAL_CONTEXT_KEY = "additionalContext"
ROUTED_CONTEXT_TEMPLATE = (
    "Subagent model and effort rule: this {family} spawn now runs at {effort} effort."
)
