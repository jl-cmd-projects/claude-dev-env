"""Constants for the subagent model pin PreToolUse hook.

Groups: the model every subagent runs on, the model families the hook moves,
and the hook input and output keys.
"""

from __future__ import annotations

SUBAGENT_MODEL_ALIAS = "opus"
ALL_MOVED_MODEL_FAMILIES = ("sonnet", "haiku")
MODEL_INPUT_KEY = "model"
TOOL_INPUT_KEY = "tool_input"
CONTEXT_PREFIX = "Subagent model moved to opus (was "
CONTEXT_OMITTED_MODEL_TEXT = "inherited from the parent"
CONTEXT_SUFFIX = ")."
ADDITIONAL_CONTEXT_KEY = "additionalContext"
