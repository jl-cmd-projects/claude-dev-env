"""The context budget command checks explicit files against HEAD and keeps the list generated."""

from __future__ import annotations

import io
import json
import subprocess
import sys
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


def _hook_policy(repository_root: Path, all_hook_specs: list[tuple[str, str]]) -> Path:
    all_hooks = []
    for index, (name, source_text) in enumerate(all_hook_specs):
        hook_path = repository_root / f"fixture_hook_{index}.py"
        hook_path.write_text(source_text, encoding="utf-8")
        all_hooks.append(
            {
                "name": name,
                "command": [sys.executable, str(hook_path)],
                "stdin": {},
                "char_limit": 1500,
            }
        )
    policy_path = repository_root / ".claude" / "context-budget.json"
    policy_path.write_text(
        json.dumps(
            {
                "kinds": [],
                "hooks": all_hooks,
                "baseline": {"files": {}, "hooks": {"sample": 2200}},
            }
        ),
        encoding="utf-8",
    )
    return policy_path


def _hook_cli(repository_root: Path, action: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, context_budget_check.__file__, action],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("action", ["--hooks", "--write-baseline"])
def test_duplicate_hook_names_fail_without_replacing_the_policy(
    repository_root: Path,
    action: str,
) -> None:
    policy_path = _hook_policy(
        repository_root,
        [
            ("sample", "print('x' * 2100)\n"),
            ("sample", "print('x')\n"),
        ],
    )
    prior_text = policy_path.read_bytes()

    completed = _hook_cli(repository_root, action)

    assert completed.returncode == 1
    assert "hook names must be unique" in completed.stdout
    assert policy_path.read_bytes() == prior_text


@pytest.mark.parametrize("action", ["--hooks", "--write-baseline"])
@pytest.mark.parametrize(
    "source_text",
    [
        "raise RuntimeError('fixture failure')\n",
        "print('partial output')\nraise RuntimeError('fixture failure')\n",
    ],
)
def test_failed_hook_measurement_fails_without_replacing_the_policy(
    repository_root: Path,
    action: str,
    source_text: str,
) -> None:
    policy_path = _hook_policy(repository_root, [("sample", source_text)])
    prior_text = policy_path.read_bytes()

    completed = _hook_cli(repository_root, action)

    assert completed.returncode == 1
    assert 'hook "sample" exited with status 1' in completed.stdout
    assert "fixture failure" in completed.stdout
    assert policy_path.read_bytes() == prior_text


def test_unique_hook_measurements_keep_each_count(repository_root: Path) -> None:
    _hook_policy(
        repository_root, [("sample", "print('x' * 2100)\n"), ("short", "print('x')\n")]
    )

    completed = _hook_cli(repository_root, "--hooks")

    assert completed.returncode == 0
    assert "sample: 2101 characters" in completed.stdout
    assert "short: 2 characters" in completed.stdout


def test_successful_empty_hook_can_remove_its_baseline(repository_root: Path) -> None:
    policy_path = _hook_policy(repository_root, [("sample", "")])

    completed = _hook_cli(repository_root, "--write-baseline")

    assert completed.returncode == 0
    assert (
        json.loads(policy_path.read_text(encoding="utf-8"))["baseline"]["hooks"] == {}
    )


def test_successful_hook_baseline_preserves_its_count(repository_root: Path) -> None:
    policy_path = _hook_policy(repository_root, [("sample", "print('x' * 2100)\n")])

    completed = _hook_cli(repository_root, "--write-baseline")

    assert completed.returncode == 0
    assert json.loads(policy_path.read_text(encoding="utf-8"))["baseline"]["hooks"] == {
        "sample": 2101
    }


def test_a_unique_unlisted_long_hook_still_exceeds_its_limit(
    repository_root: Path,
) -> None:
    policy_path = _hook_policy(repository_root, [("sample", "print('x' * 2100)\n")])
    raw_policy = json.loads(policy_path.read_text(encoding="utf-8"))
    raw_policy["baseline"]["hooks"] = {}
    policy_path.write_text(json.dumps(raw_policy), encoding="utf-8")

    completed = _hook_cli(repository_root, "--hooks")

    assert completed.returncode == 1
    assert "injects 2101 characters (limit 1500)" in completed.stdout
