"""Read the review rules named by settings."""

from __future__ import annotations

from pathlib import Path

from tools.config import efficient_review_constants as skill_constants
from tools.config import review_run_constants as c
from tools.config.efficient_review_settings import load_settings, string_list
from tools.efficient_review_request import ReviewRequestRunFatal


def review_rules_text(rules_root: Path | None = None) -> str:
    """Return every configured review rules file under its own heading.

    Args:
        rules_root: The directory that holds the rules. Empty uses settings,
            then a parent of this skill that already contains the first path.

    Returns:
        The rules text with one heading per source file.

    Raises:
        ReviewRequestRunFatal: A configured rules file is missing.
    """
    all_settings = load_settings()
    root = rules_root or _resolved_rules_root(all_settings)
    all_sections: list[str] = []
    for each_relative_path in string_list(all_settings, "rules_paths"):
        _append_rules_file(all_sections, root, each_relative_path)
    return c.PROMPT_SECTION_SEPARATOR.join(all_sections)


def _resolved_rules_root(all_settings: dict[str, object]) -> Path:
    configured = str(all_settings.get("rules_root") or "")
    if configured:
        return Path(configured)
    all_paths = string_list(all_settings, "rules_paths")
    if not all_paths:
        raise ReviewRequestRunFatal("settings rules_paths is empty")
    found = _rules_root_from_parents(skill_constants.SKILL_ROOT, all_paths[0])
    if found is None:
        raise ReviewRequestRunFatal(
            "set rules_root in settings to the directory that holds the review rules"
        )
    return found


def _rules_root_from_parents(start: Path, relative_path: str) -> Path | None:
    current = start.resolve()
    remaining_steps = skill_constants.PARENT_WALK_LIMIT
    while remaining_steps:
        if (current / relative_path).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent
        remaining_steps -= 1
    return None


def _append_rules_file(all_sections: list[str], root: Path, relative_path: str) -> None:
    rules_path = root / relative_path
    if not rules_path.is_file():
        raise ReviewRequestRunFatal(f"review rules file is missing: {rules_path}")
    all_sections.append(c.REVIEW_RULES_HEADING_TEMPLATE.format(path=relative_path))
    all_sections.append(rules_path.read_text(encoding=c.TEXT_ENCODING).strip())
