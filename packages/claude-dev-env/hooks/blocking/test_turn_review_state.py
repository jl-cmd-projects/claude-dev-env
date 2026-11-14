import json
import os
import tempfile
from pathlib import Path

import pytest

from turn_review_state import (
    _Finding,
    _is_lock_taken,
    _load_state,
    _log,
    _next_finding_id,
    _release_and_close,
    _ReviewState,
    _save_state,
    _state_path,
)

SESSION_ID = "state-session"
BASE_COMMIT = "a" * 40
TURN_COMMIT = "b" * 40


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setattr(tempfile, "tempdir", str(state_directory))
    return home_directory


def log_lines(home_directory: Path) -> list[str]:
    log_path = home_directory / ".claude" / "logs" / "turn-review.log"
    return log_path.read_text().splitlines() if log_path.exists() else []


def test_should_load_every_field_a_save_wrote() -> None:
    saved_state = _ReviewState(
        all_baselines={"/work/app": BASE_COMMIT},
        blocks_in_a_row=2,
        is_turn_open=True,
        last_wake_at=100.5,
        open_turn_prompt_at=90.0,
        all_findings={
            "TR-3": _Finding(
                "src/service.py:3 - drops the retry",
                "/work/app",
                BASE_COMMIT,
                TURN_COMMIT,
                "upheld",
                "Nothing retries.",
            )
        },
    )
    _save_state(SESSION_ID, saved_state)
    assert _state_path(SESSION_ID).name == "turn-review-state-session.json"
    assert _load_state(SESSION_ID) == saved_state


def test_should_leave_out_saved_entries_in_another_form() -> None:
    finding_record = {
        "text": "src/service.py:3 - drops the retry",
        "repository": "/work/app",
        "base": BASE_COMMIT,
        "turn": TURN_COMMIT,
        "status": "open",
        "judge_reason": None,
    }
    _state_path(SESSION_ID).write_text(
        json.dumps(
            {
                "baselines": {"/work/app": BASE_COMMIT, "/work/lib": "HEAD~1"},
                "blocks_in_a_row": 1,
                "turn_open": 1,
                "last_wake_at": True,
                "findings": {
                    "TR-1": finding_record,
                    "TR-01": finding_record,
                    "TR-2": {**finding_record, "status": "closed"},
                    "TR-4": {**finding_record, "turn": "main"},
                },
            }
        )
    )
    loaded_state = _load_state(SESSION_ID)
    assert loaded_state.all_baselines == {"/work/app": BASE_COMMIT}
    assert loaded_state.blocks_in_a_row == 1
    assert loaded_state.is_turn_open is False
    assert loaded_state.last_wake_at is None
    assert list(loaded_state.all_findings) == ["TR-1"]


def test_should_give_an_empty_state_for_a_file_that_is_not_json() -> None:
    _state_path(SESSION_ID).write_text("{not json")
    assert _load_state(SESSION_ID) == _ReviewState()


def test_should_number_the_next_finding_after_the_highest_id() -> None:
    finding = _Finding("text", "/work/app", BASE_COMMIT, TURN_COMMIT)
    review_state = _ReviewState(all_findings={"TR-2": finding, "TR-10": finding})
    assert _next_finding_id(review_state) == "TR-11"
    assert _next_finding_id(_ReviewState()) == "TR-1"


def test_should_log_one_dated_line_each_call_and_log_a_failed_save(isolated_home: Path) -> None:
    _log("[turn_review_gate] first\n")
    _log("[turn_review_gate] second\n")
    _state_path(SESSION_ID).mkdir()
    _save_state(SESSION_ID, _ReviewState(blocks_in_a_row=1))
    all_lines = log_lines(isolated_home)
    assert len(all_lines) == 3
    assert all_lines[0].endswith(" [turn_review_gate] first")
    assert all_lines[0][:4].isdigit()
    assert all_lines[1].endswith(" [turn_review_gate] second")
    assert "[turn_review_gate] the review state was not saved: " in all_lines[2]


def test_should_refuse_a_second_lock_until_the_first_is_released(tmp_path: Path) -> None:
    lock_path = tmp_path / "state.lock"
    lock_path.write_text("x")
    first_descriptor = os.open(lock_path, os.O_RDWR)
    second_descriptor = os.open(lock_path, os.O_RDWR)
    assert _is_lock_taken(first_descriptor) is True
    assert _is_lock_taken(second_descriptor) is False
    _release_and_close(first_descriptor, True)
    assert _is_lock_taken(second_descriptor) is True
    _release_and_close(second_descriptor, True)
