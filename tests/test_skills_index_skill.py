"""Source-contract tests for the claude-dev-env skills index skill."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SKILLS_PATH = (
    REPOSITORY_ROOT / "packages" / "claude-dev-env" / ".agents" / "skills"
)
INDEX_NAME = "dev-env-skills-index"
INDEX_PATH = SHIPPED_SKILLS_PATH / INDEX_NAME / "SKILL.md"
TABLE_HEADER_LINE = "| Skill | Use when | Path |"
DESCRIPTION_PREFIX = "description: "
MAX_DESCRIPTION_LENGTH = 200


def _read(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def _frontmatter_and_body(skill_text: str) -> tuple[list[str], list[str]]:
    _, frontmatter_block, body_block = skill_text.split("---\n", 2)
    return frontmatter_block.splitlines(), body_block.splitlines()


def _non_blank_lines(body_lines: list[str]) -> list[str]:
    return [each_line for each_line in body_lines if each_line.strip()]


def _data_rows(body_lines: list[str]) -> list[tuple[str, ...]]:
    _, _, *data_lines = _non_blank_lines(body_lines)
    return [
        tuple(
            each_cell.strip() for each_cell in each_line.strip().strip("|").split("|")
        )
        for each_line in data_lines
    ]


def test_skills_index_frontmatter_keeps_model_invocation_on() -> None:
    frontmatter_lines, _ = _frontmatter_and_body(_read(INDEX_PATH))

    assert f"name: {INDEX_NAME}" in frontmatter_lines
    assert not any(
        each_line.startswith("disable-model-invocation")
        for each_line in frontmatter_lines
    )


def test_skills_index_description_fits_the_length_limit() -> None:
    frontmatter_lines, _ = _frontmatter_and_body(_read(INDEX_PATH))
    description_line = next(
        (
            each_line
            for each_line in frontmatter_lines
            if each_line.startswith(DESCRIPTION_PREFIX)
        ),
        "",
    )
    description = description_line.removeprefix(DESCRIPTION_PREFIX)

    assert description, "frontmatter needs a description line"
    assert not description.startswith((">", "|")), "keep the description on one line"
    assert len(description) <= MAX_DESCRIPTION_LENGTH


def test_skills_index_body_is_only_the_skill_table() -> None:
    _, body_lines = _frontmatter_and_body(_read(INDEX_PATH))
    table_lines = _non_blank_lines(body_lines)

    assert all(each_line.startswith("|") for each_line in table_lines)
    assert table_lines[0] == TABLE_HEADER_LINE


def test_skills_index_lists_every_shipped_skill_once() -> None:
    _, body_lines = _frontmatter_and_body(_read(INDEX_PATH))
    listed_names = [each_row[0] for each_row in _data_rows(body_lines)]
    shipped_names = {
        each_path.parent.name
        for each_path in SHIPPED_SKILLS_PATH.glob("*/SKILL.md")
        if each_path.parent.name != INDEX_NAME
    }

    assert len(listed_names) == len(set(listed_names))
    assert set(listed_names) == shipped_names


def test_skills_index_paths_open_each_listed_skill_file() -> None:
    _, body_lines = _frontmatter_and_body(_read(INDEX_PATH))

    for each_name, _, each_path in _data_rows(body_lines):
        resolved_path = (INDEX_PATH.parent / each_path).resolve()
        assert resolved_path == (SHIPPED_SKILLS_PATH / each_name / "SKILL.md").resolve()
        assert resolved_path.is_file()


def test_skills_index_names_match_each_listed_skill_frontmatter() -> None:
    _, body_lines = _frontmatter_and_body(_read(INDEX_PATH))

    for each_name, _, _ in _data_rows(body_lines):
        frontmatter_lines, _ = _frontmatter_and_body(
            _read(SHIPPED_SKILLS_PATH / each_name / "SKILL.md")
        )
        assert f"name: {each_name}" in frontmatter_lines
