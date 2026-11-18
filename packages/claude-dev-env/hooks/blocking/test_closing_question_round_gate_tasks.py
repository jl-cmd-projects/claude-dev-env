import json
from pathlib import Path

import pytest

from hooks_constants.closing_question_round_gate_constants import (
    IN_PROGRESS_TASKS_REASON_LEAD,
)
from test_closing_question_round_gate import (
    SESSION_ID,
    held_reason,
    reply_record,
    stop_feedback_record,
    tool_call_record,
    tool_result_record,
    typed_prompt_record,
)
from test_closing_question_round_gate_work import DECLARATION

MAIN_GOAL_SUBJECT = "P1: 44/99 landed"
SIDE_PROMPT = "Why is the lint check red on 8774?"
NOTHING_OPEN_CARD_ANSWER = "The user chose No, nothing to add."
IN_PROGRESS_FEEDBACK_TEXT = f"Stop hook feedback:\n{IN_PROGRESS_TASKS_REASON_LEAD}"


@pytest.fixture(autouse=True)
def scratch_task_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)


def write_task_store(tmp_path: Path, all_task_entries: list[dict[str, str]]) -> None:
    task_directory = tmp_path / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True)
    for each_entry in all_task_entries:
        (task_directory / f"{each_entry['id']}.json").write_text(
            json.dumps(each_entry), encoding="utf-8"
        )


def nothing_open_records() -> list[dict[str, object]]:
    return [
        typed_prompt_record(SIDE_PROMPT),
        reply_record("The lint check is red because the line is too long."),
        tool_call_record(
            "AskUserQuestion", {"questions": [{"question": "Nothing is open. Add an item?"}]}
        ),
        tool_result_record("AskUserQuestion", NOTHING_OPEN_CARD_ANSWER),
        reply_record(f"Nothing to add.\n\n{DECLARATION}"),
    ]


def test_should_hold_the_declaration_while_a_task_store_item_is_in_progress(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(
        tmp_path,
        [
            {"id": "1", "subject": "P0: 5/6 landed", "status": "completed"},
            {"id": "2", "subject": MAIN_GOAL_SUBJECT, "status": "in_progress"},
        ],
    )
    reason = str(held_reason(monkeypatch, capsys, tmp_path, nothing_open_records()))
    assert reason.startswith(IN_PROGRESS_TASKS_REASON_LEAD)
    assert f"- {MAIN_GOAL_SUBJECT} [landed]" in reason
    assert "P0: 5/6 landed" not in reason


def test_should_hold_the_declaration_while_the_transcript_task_list_has_an_in_progress_item(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record("Merge every open P0 to P4 pull request."),
        tool_call_record("TaskCreate", {"subject": MAIN_GOAL_SUBJECT}, tool_use_id="create-1"),
        tool_result_record("TaskCreate", "Task #7 created successfully", tool_use_id="create-1"),
        tool_call_record(
            "TaskUpdate", {"taskId": "7", "status": "in_progress"}, tool_use_id="update-1"
        ),
        tool_result_record("TaskUpdate", "Updated task #7 status", tool_use_id="update-1"),
        *nothing_open_records(),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(IN_PROGRESS_TASKS_REASON_LEAD)
    assert f"- {MAIN_GOAL_SUBJECT} [landed]" in reason


@pytest.mark.parametrize("task_status", ["completed", "pending", "deleted"])
def test_should_allow_the_declaration_when_no_task_is_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    task_status: str,
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": MAIN_GOAL_SUBJECT, "status": task_status}])
    assert held_reason(monkeypatch, capsys, tmp_path, nothing_open_records()) is None


def test_should_allow_a_closing_reply_with_no_declaration_and_no_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": MAIN_GOAL_SUBJECT, "status": "in_progress"}])
    all_records = [typed_prompt_record(SIDE_PROMPT), reply_record("The line is too long.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_count_its_own_holds_and_allow_the_third_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": MAIN_GOAL_SUBJECT, "status": "in_progress"}])
    held_twice_records = [
        *nothing_open_records(),
        stop_feedback_record(IN_PROGRESS_FEEDBACK_TEXT),
        reply_record(DECLARATION),
        stop_feedback_record(IN_PROGRESS_FEEDBACK_TEXT),
        reply_record(DECLARATION),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, held_twice_records) is None
