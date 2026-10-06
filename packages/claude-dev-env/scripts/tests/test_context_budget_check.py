"""The context budget command checks explicit files against HEAD and keeps the list generated."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import context_budget_check
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SKILL_RELATIVE_PATH = "skills/example/SKILL.md"


def _git(repository_root: Path, *all_arguments: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            *all_arguments,
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )


def _section(heading: str, detail_count: int) -> str:
    return f"## {heading}\n" + "".join(
        f"Detail line {each}.\n" for each in range(detail_count)
    )


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    policy = {
        "section_detail_line_limit": 6,
        "kinds": [
            {
                "name": "skill entry",
                "patterns": ["**/SKILL.md"],
                "line_limit": 10,
                "section_rule": True,
            }
        ],
        "hooks": [],
        "baseline": {
            "files": {SKILL_RELATIVE_PATH: {"lines": 20, "sections": ["Plan"]}},
            "hooks": {},
        },
    }
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "context-budget.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    skill_path = tmp_path / SKILL_RELATIVE_PATH
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(_section("Plan", 7) + "\n" * 12, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return tmp_path


def _run(repository_root: Path, *all_arguments: str) -> tuple[int, str]:
    stdout = io.StringIO()
    exit_code = context_budget_check.main(list(all_arguments), repository_root, stdout)
    return exit_code, stdout.getvalue()


def test_an_unchanged_listed_file_is_ok(repository_root: Path) -> None:
    exit_code, report_text = _run(
        repository_root, str(repository_root / SKILL_RELATIVE_PATH)
    )

    assert exit_code == 0
    assert "context-budget: OK (1 checked)" in report_text


def test_head_is_the_prior_state_so_a_shrunk_listed_file_must_lower_its_entry(
    repository_root: Path,
) -> None:
    (repository_root / SKILL_RELATIVE_PATH).write_text(
        _section("Plan", 7) + "\n" * 4, encoding="utf-8"
    )

    exit_code, report_text = _run(
        repository_root, str(repository_root / SKILL_RELATIVE_PATH)
    )

    assert exit_code == 1
    assert '{"lines": 12, "sections": ["Plan"]}' in report_text


def test_a_new_unpointed_section_is_reported(repository_root: Path) -> None:
    skill_path = repository_root / SKILL_RELATIVE_PATH
    skill_path.write_text(_section("Plan", 7) + _section("Steps", 7), encoding="utf-8")

    exit_code, report_text = _run(repository_root, str(skill_path))

    assert exit_code == 1
    assert 'section "Steps" has 7 detail lines' in report_text


def test_write_baseline_records_the_tree(repository_root: Path) -> None:
    (repository_root / SKILL_RELATIVE_PATH).write_text(
        _section("Plan", 7) + "\n" * 4, encoding="utf-8"
    )

    exit_code, report_text = _run(repository_root, "--write-baseline")

    written = json.loads(
        (repository_root / ".claude" / "context-budget.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0 and "1 files" in report_text
    assert written["baseline"]["files"] == {
        SKILL_RELATIVE_PATH: {"lines": 12, "sections": ["Plan"]}
    }


def test_the_committed_baseline_matches_what_the_generator_builds_today() -> None:
    policy = context_budget_check.read_policy_file(REPOSITORY_ROOT)
    assert policy is not None
    committed = json.loads(
        (REPOSITORY_ROOT / ".claude" / "context-budget.json").read_text(
            encoding="utf-8"
        )
    )

    regenerated = context_budget_check.current_baseline(policy, REPOSITORY_ROOT)

    assert regenerated == committed["baseline"]
