"""Names and pointer text for the artifact_template_pointer PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_QUICKSTART_ACTION",
    "ARTIFACT_TEMPLATE_PATH",
    "ARTIFACT_TOOL_NAME",
    "ALTERNATIVE_TEXT_PREFIX",
    "DEFAULT_TEMPLATE_INSTALL_COMMAND",
    "DEFAULT_TEMPLATE_SKILL_NAME",
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
    Path(__file__).resolve().parents[2] / "docs" / "templates" / "artifact-page" / "template.html"
)
DEFAULT_TEMPLATE_SKILL_NAME = "html-plan:html-plan"
DEFAULT_TEMPLATE_INSTALL_COMMAND = (
    "claude plugin marketplace add anthropics/claude-plugins-community"
    " && claude plugin install html-plan@claude-community"
)
POINTER_TEXT_PREFIX = "Build this artifact page from the html-plan skill, "
ALTERNATIVE_TEXT_PREFIX = "Alternative: the template at "
