"""The grader scores a replay. It does not rewrite the task."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import grade_role_stack_replay as grader

_FIXTURE_PATH = _SESSION_DIR / "fixtures" / "role_stack_replay.json"


def test_should_score_the_login_failure_example_without_rewriting() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    all_scores = grader.score_fixture(fixture)
    assert [each_score["name"] for each_score in all_scores] == ["known_bad", "known_good"]
    assert all_scores[0]["score"] == "refuse"
    assert all_scores[0]["reason"] == "example-noun-in-scope"
    assert all_scores[1]["score"] == "accept"
    assert all(each_score["matched"] == "yes" for each_score in all_scores)


def test_should_leave_the_task_text_unchanged_in_the_fixture() -> None:
    fixture_text = _FIXTURE_PATH.read_text(encoding="utf-8")
    grader.score_fixture(json.loads(fixture_text))
    assert _FIXTURE_PATH.read_text(encoding="utf-8") == fixture_text
    assert "For example, the login failure." in fixture_text


def test_should_exit_zero_when_the_fixture_matches() -> None:
    completed = subprocess.run(
        [sys.executable, str(_SESSION_DIR / "grade_role_stack_replay.py"), str(_FIXTURE_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "example-noun-in-scope" in completed.stdout
    assert '"score": "accept"' in completed.stdout
