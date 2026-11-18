from pathlib import Path

import pytest

from closing_question_round_tasks import session_tasks
from test_closing_question_round_gate import SESSION_ID
from test_closing_question_round_gate_tasks import (
    MAIN_GOAL_SUBJECT,
    write_task_store,
)


def test_should_split_the_task_store_into_in_progress_and_still_open_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    write_task_store(
        tmp_path,
        [
            {"id": "2", "subject": "P0 counts", "status": "completed"},
            {"id": "3", "subject": MAIN_GOAL_SUBJECT, "status": "in_progress"},
            {"id": "4", "subject": "P2 counts", "status": "pending"},
        ],
    )
    all_tasks = session_tasks({"session_id": SESSION_ID})
    assert [each_task.item_id for each_task in all_tasks.in_progress] == ["3"]
    assert [each_task.item_id for each_task in all_tasks.still_open] == ["3", "4"]


def test_should_read_the_transcript_task_calls_when_no_store_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    all_tasks = session_tasks({"session_id": SESSION_ID, "transcript_path": str(tmp_path / "none.jsonl")})
    assert all_tasks.in_progress == ()
    assert all_tasks.still_open == ()
