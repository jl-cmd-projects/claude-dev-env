"""Each rule entry keeps the index shape, and the always-loaded entries stay inside a byte budget."""

import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
RULES_DIRECTORY = PACKAGE_ROOT / "rules"
RULE_GUIDES_DIRECTORY = PACKAGE_ROOT / "docs" / "rule-guides"

module_directory = str(Path(__file__).parents[1])
if module_directory not in sys.path:
    sys.path.insert(0, module_directory)

from codex_compat_materializer import (
    codex_instruction_rule_relative_paths,
    instruction_alias_filenames,
)

FRONTMATTER_DELIMITER = "---"
FULL_TEXT_LINK_PATTERN = re.compile(
    r"^\*\*Full text:\*\*.*?\]\((\.\./docs/rule-guides/[^)#\s]+\.md)\)", re.MULTILINE
)
TITLE_PATTERN = re.compile(r"^# \S", re.MULTILINE)

MAXIMUM_ENTRY_BYTES = 2_000
MAXIMUM_ALWAYS_ON_BYTES = 40_000
POINTER_ENTRY_NAMES: frozenset[str] = frozenset()
CODEX_MATERIALIZED_GUIDE_NAMES = frozenset(
    Path(each_path).name for each_path in codex_instruction_rule_relative_paths
)


def _entry_paths() -> list[Path]:
    return sorted(
        each_path
        for each_path in RULES_DIRECTORY.glob("*.md")
        if each_path.name not in instruction_alias_filenames
    )


def _split_frontmatter(entry_text: str) -> tuple[list[str], str]:
    all_lines = entry_text.splitlines()
    if not all_lines or all_lines[0] != FRONTMATTER_DELIMITER:
        return [], entry_text
    for each_index, each_line in enumerate(all_lines[1:], start=1):
        if each_line == FRONTMATTER_DELIMITER:
            return all_lines[1:each_index], "\n".join(all_lines[each_index + 1 :])
    return [], entry_text


def _loads_in_every_session(entry_text: str) -> bool:
    all_frontmatter_lines, _ = _split_frontmatter(entry_text)
    return not any(
        each_line.startswith("paths:") for each_line in all_frontmatter_lines
    )


def _linked_guide_names(entry_text: str) -> set[str]:
    return {
        Path(each_target).name
        for each_target in FULL_TEXT_LINK_PATTERN.findall(entry_text)
    }


def _entry_text(entry_path: Path) -> str:
    return entry_path.read_text(encoding="utf-8")


def test_each_entry_stays_inside_the_entry_byte_budget() -> None:
    over_budget = {
        each_path.name: len(each_path.read_bytes())
        for each_path in _entry_paths()
        if len(each_path.read_bytes()) > MAXIMUM_ENTRY_BYTES
    }
    assert over_budget == {}


def test_each_entry_opens_with_a_title_after_its_frontmatter() -> None:
    untitled = [
        each_path.name
        for each_path in _entry_paths()
        if not TITLE_PATTERN.match(
            _split_frontmatter(_entry_text(each_path))[1].lstrip()
        )
    ]
    assert untitled == []


def _full_text_link_problems(entry_path: Path) -> list[str]:
    all_guide_names = _linked_guide_names(_entry_text(entry_path))
    if not all_guide_names:
        return [f"{entry_path.name}: no Full text link"]
    return [
        f"{entry_path.name}: {each_guide_name} does not exist"
        for each_guide_name in sorted(all_guide_names)
        if not (RULE_GUIDES_DIRECTORY / each_guide_name).is_file()
    ]


def test_each_entry_links_a_full_text_guide_that_exists() -> None:
    all_problems = [
        each_problem
        for each_path in _entry_paths()
        if each_path.name not in POINTER_ENTRY_NAMES
        for each_problem in _full_text_link_problems(each_path)
    ]
    assert all_problems == []


def test_each_guide_has_exactly_one_owner() -> None:
    owners_by_guide: dict[str, list[str]] = {}
    for each_path in _entry_paths():
        for each_guide_name in _linked_guide_names(_entry_text(each_path)):
            owners_by_guide.setdefault(each_guide_name, []).append(each_path.name)
    unowned = sorted(
        each_guide.name
        for each_guide in RULE_GUIDES_DIRECTORY.glob("*.md")
        if each_guide.name not in owners_by_guide
        and each_guide.name not in CODEX_MATERIALIZED_GUIDE_NAMES
    )
    shared = {
        each_guide_name: all_owner_names
        for each_guide_name, all_owner_names in owners_by_guide.items()
        if len(all_owner_names) > 1
    }
    assert unowned == []
    assert shared == {}


def test_always_loaded_entries_stay_inside_the_total_byte_budget() -> None:
    always_on_bytes = sum(
        len(each_path.read_bytes())
        for each_path in _entry_paths()
        if _loads_in_every_session(_entry_text(each_path))
    )
    assert always_on_bytes <= MAXIMUM_ALWAYS_ON_BYTES
