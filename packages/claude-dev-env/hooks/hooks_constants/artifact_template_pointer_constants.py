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
    "STATUS_FLOWCHART_POINTER_PREFIX",
    "STATUS_FLOWCHART_TEMPLATE_PATH",
    "ALL_ARTIFACT_DESIGN_SKILL_NAMES",
]

ARTIFACT_TOOL_NAME = "Artifact"
ARTIFACT_ACTION_INPUT_KEY = "action"
ARTIFACT_QUICKSTART_ACTION = "quickstart"
SKILL_TOOL_NAME = "Skill"
SKILL_NAME_INPUT_KEY = "skill"
ALL_ARTIFACT_DESIGN_SKILL_NAMES = frozenset({"artifact-design"})
TEMPLATES_DIRECTORY = Path(__file__).resolve().parents[2] / "docs" / "templates"
ARTIFACT_TEMPLATE_PATH = TEMPLATES_DIRECTORY / "artifact-page" / "README.md"
HTML_PLAN_TEMPLATE_README_PATH = TEMPLATES_DIRECTORY / "html-plan" / "README.md"
STATUS_FLOWCHART_TEMPLATE_PATH = TEMPLATES_DIRECTORY / "artifact-page" / "status-flowchart.html"
STATUS_FLOWCHART_POINTER_PREFIX = (
    "For a status or progress report, prefer the status flowchart: done steps,"
    " yes-or-no checks, stuck steps with recheck loops, and the next step, each"
    " opening its detail on click. Build it from "
)
POINTER_TEXT_PREFIX = (
    ", unless the person asks for another shape."
    " Otherwise pick the visual by scope. For one flow or one comparison, draw an inline SVG"
    " flowchart artifact with minimal text, using the artifact-diagramming skill."
    " For a multi-part plan or evidence, build an html-plan page following "
)
POINTER_ALTERNATIVE_PREFIX = (
    ". When the request names the older artifact page template,"
    " pick the one that fits the ask from "
)
