"""Shared builders for the context budget tests."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIRECTORY = Path(__file__).resolve().parents[2] / "test_files" / "context_budget"
ORCHESTRATOR_PATH = "packages/claude-dev-env/.agents/skills/orchestrator/SKILL.md"
SKILL_PATH = "tools/example/SKILL.md"


def fixture_text(file_name: str) -> str:
    """Return one committed fixture's text.

    Args:
        file_name: Fixture file name under ``test_files/context_budget``.

    Returns:
        The fixture text.
    """
    return (FIXTURE_DIRECTORY / file_name).read_text(encoding="utf-8")


def policy_text(baseline_files: dict | None = None) -> str:
    """Return a policy JSON text with three kinds and one hook.

    Args:
        baseline_files: Baseline file entries, or None for an empty list.

    Returns:
        Policy JSON text.
    """
    raw_policy: dict[str, object] = {
        "section_detail_line_limit": 6,
        "kinds": [
            {"name": "archived skill", "patterns": ["**/skills-archived/**"], "line_limit": None},
            {
                "name": "skill entry",
                "patterns": ["**/SKILL.md"],
                "line_limit": 200,
                "section_rule": True,
            },
            {"name": "rule", "patterns": ["rules/*.md"], "line_limit": 30, "section_rule": True},
        ],
        "hooks": [
            {"name": "greeter", "command": ["python3", "g.py"], "stdin": {}, "char_limit": 1500}
        ],
        "baseline": {"files": baseline_files or {}, "hooks": {}},
    }
    return json.dumps(raw_policy)


def section_text(heading: str, detail_count: int, pointer_line: str = "") -> str:
    """Return one Markdown section with numbered detail lines.

    Args:
        heading: Section heading text.
        detail_count: Number of detail lines.
        pointer_line: Optional extra line, such as a link.

    Returns:
        The section text ending in a newline.
    """
    all_lines = [
        f"## {heading}",
        *(f"Detail line {each} of the section." for each in range(detail_count)),
    ]
    if pointer_line:
        all_lines.append(pointer_line)
    return "\n".join(all_lines) + "\n"
