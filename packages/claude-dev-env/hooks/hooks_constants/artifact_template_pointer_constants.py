"""Names and pointer text for the artifact_template_pointer PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_QUICKSTART_ACTION",
    "ARTIFACT_TEMPLATE_PATH",
    "ARTIFACT_TOOL_NAME",
    "HTML_PLAN_TEMPLATE_README_PATH",
    "POINTER_ALTERNATIVE_PREFIX",
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
TEMPLATES_DIRECTORY = Path(__file__).resolve().parents[2] / "docs" / "templates"
ARTIFACT_TEMPLATE_PATH = TEMPLATES_DIRECTORY / "artifact-page" / "template.html"
HTML_PLAN_TEMPLATE_README_PATH = TEMPLATES_DIRECTORY / "html-plan" / "README.md"
POINTER_TEXT_PREFIX = "Build this artifact page from the html-plan skill, following "
POINTER_ALTERNATIVE_PREFIX = ". When the request names the older artifact page template, build from "
