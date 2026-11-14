"""Constants for the subagent effort route.

Groups: where the hand-edited effort levels file lives and the keys it uses,
the built-in levels used when that file is missing or invalid, the tool input
keys, and the hook output text.
"""

from __future__ import annotations

from pathlib import Path

EFFORT_LEVELS_PATH = Path(__file__).resolve().parent / "subagent_effort_levels.json"
ALLOWED_EFFORTS_KEY = "allowed"
DEFAULT_EFFORT_KEY = "default"
EFFORT_LEVELS_FALLBACK_DIAGNOSTIC = (
    "subagent effort route: {path} is missing or invalid ({problem}); using the built-in effort levels.\n"
)
ALL_KNOWN_EFFORT_NAMES = ("low", "medium", "high", "xhigh", "max")

ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY: dict[str, dict[str, object]] = {
    "opus": {ALLOWED_EFFORTS_KEY: ("medium", "high"), DEFAULT_EFFORT_KEY: "medium"},
    "sonnet": {ALLOWED_EFFORTS_KEY: ("high",), DEFAULT_EFFORT_KEY: "high"},
    "fable": {ALLOWED_EFFORTS_KEY: ("low", "medium", "high"), DEFAULT_EFFORT_KEY: "high"},
    "haiku": {
        ALLOWED_EFFORTS_KEY: ("low", "medium", "high", "xhigh", "max"),
        DEFAULT_EFFORT_KEY: "medium",
    },
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
