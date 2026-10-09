"""Names and pointer text for the artifact_template_pointer PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_QUICKSTART_ACTION",
    "ARTIFACT_TEMPLATE_PATH",
    "ARTIFACT_TOOL_NAME",
    "POINTER_TEXT_PREFIX",
    "SKILL_NAME_INPUT_KEY",
    "SKILL_TOOL_NAME",
    "ALL_ARTIFACT_DESIGN_SKILL_NAMES",
]

ARTIFACT_TOOL_NAME = "Artifact"
ARTIFACT_ACTION_INPUT_KEY = "action"
ARTIFACT_QUICKSTART_ACTION = "quickstart"
SKILL_TOOL_NAME = "Skill"
SKILL_NAME_INPUT_KEY = "skill"
ALL_ARTIFACT_DESIGN_SKILL_NAMES = frozenset({"artifact-design"})
ARTIFACT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "templates" / "artifact-page" / "README.md"
)
POINTER_TEXT_PREFIX = "Pick the artifact page template that fits the ask from "
