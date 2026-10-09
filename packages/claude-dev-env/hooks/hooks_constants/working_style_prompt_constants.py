"""Working-style prompt text for the SessionStart working_style_prompt hook."""

from __future__ import annotations

__all__ = [
    "WORKING_STYLE_GUIDE_RELATIVE_PATH",
    "WORKING_STYLE_PROMPT",
]

WORKING_STYLE_GUIDE_RELATIVE_PATH = "docs/references/working-style.md"

WORKING_STYLE_PROMPT = (
    f"Read ~/.claude/{WORKING_STYLE_GUIDE_RELATIVE_PATH} before your first reply. "
    "It sets how you keep task records, present answers, reply, hold scope, and "
    "ask questions."
)
