import importlib.util
import json
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parent
run_specification = importlib.util.spec_from_file_location(
    "closing_round_run", flow_directory / "run.py"
)
closing_round_run = importlib.util.module_from_spec(run_specification)
run_specification.loader.exec_module(closing_round_run)

ALWAYS_ALLOW_SOURCE = "import sys\nsys.exit(0)\n"
ALWAYS_HOLD_SOURCE = 'import sys\nsys.stdout.write(\'{"decision": "block", "reason": "held"}\')\nsys.exit(2)\n'
OPEN_ITEM_CASE = {
    "id": "open-item",
    "expected": "hold",
    "transcript": [
        {
            "type": "user",
            "turnOrigin": "human",
            "message": {"role": "user", "content": "Add the retry flag."},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "The backoff setting is deferred."}
                ],
            },
        },
    ],
}
CLOSED_CASE = {
    "id": "closed",
    "expected": "allow",
    "transcript": [
        {
            "type": "user",
            "turnOrigin": "human",
            "message": {"role": "user", "content": "Add the retry flag."},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "The retry flag is in place."}],
            },
        },
    ],
}


def stub_hook(tmp_path: Path, source_text: str) -> Path:
    hook_path = tmp_path / "stub_gate.py"
    hook_path.write_text(source_text, encoding="utf-8")
    return hook_path


def test_stop_payload_writes_the_transcript_and_adds_the_case_fields(
    tmp_path: Path,
) -> None:
    payload = closing_round_run.stop_payload(
        {**OPEN_ITEM_CASE, "payload": {"agent_id": "agent-1"}}, tmp_path
    )
    all_written_lines = (
        Path(payload["transcript_path"]).read_text(encoding="utf-8").split("\n")
    )
    assert [json.loads(each_line) for each_line in all_written_lines] == OPEN_ITEM_CASE[
        "transcript"
    ]
    assert payload["hook_event_name"] == "Stop"
    assert payload["agent_id"] == "agent-1"


def test_stop_payload_points_a_null_transcript_at_a_missing_file(
    tmp_path: Path,
) -> None:
    payload = closing_round_run.stop_payload(
        {"id": "missing", "expected": "allow", "transcript": None}, tmp_path
    )
    assert not Path(payload["transcript_path"]).exists()


def test_case_environment_is_interactive_unless_the_case_says_otherwise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    interactive_environment = closing_round_run.case_environment(
        OPEN_ITEM_CASE, tmp_path
    )
    assert interactive_environment["CLAUDE_CODE_SESSION_ATTENDED"] == "1"
    assert interactive_environment["HOME"] == str(tmp_path / "home")
    headless_case = {
        **OPEN_ITEM_CASE,
        "environment": {"CLAUDE_CODE_SESSION_ATTENDED": "0"},
    }
    assert (
        closing_round_run.case_environment(headless_case, tmp_path)[
            "CLAUDE_CODE_SESSION_ATTENDED"
        ]
        == "0"
    )


@pytest.mark.parametrize(
    ("exit_code", "stdout_text", "expected_decision"),
    [
        (2, '{"decision": "block", "reason": "held"}', "hold"),
        (0, "", "allow"),
        (0, '{"decision": "block"}', "unreadable"),
        (2, "", "unreadable"),
        (2, '{"decision": "approve"}', "unreadable"),
        (1, "", "unreadable"),
    ],
)
def test_graded_decision_reads_the_exit_code_and_stdout(
    exit_code: int, stdout_text: str, expected_decision: str
) -> None:
    assert (
        closing_round_run.graded_decision(exit_code, stdout_text) == expected_decision
    )


def test_case_decision_runs_the_gate_on_the_case() -> None:
    assert (
        closing_round_run.case_decision(OPEN_ITEM_CASE, closing_round_run.HOOK_FILE)
        == "hold"
    )
    assert (
        closing_round_run.case_decision(CLOSED_CASE, closing_round_run.HOOK_FILE)
        == "allow"
    )


def test_graded_rows_miss_the_hold_case_for_a_gate_that_always_allows(
    tmp_path: Path,
) -> None:
    all_rows = closing_round_run.graded_rows(
        [OPEN_ITEM_CASE, CLOSED_CASE], stub_hook(tmp_path, ALWAYS_ALLOW_SOURCE)
    )
    assert [has_passed for has_passed, _ in all_rows] == [False, True]
    assert all_rows[0][1] == "MISS open-item: expected hold, got allow"


def test_graded_rows_miss_the_allow_case_for_a_gate_that_always_holds(
    tmp_path: Path,
) -> None:
    all_rows = closing_round_run.graded_rows(
        [OPEN_ITEM_CASE, CLOSED_CASE], stub_hook(tmp_path, ALWAYS_HOLD_SOURCE)
    )
    assert [has_passed for has_passed, _ in all_rows] == [True, False]
    assert all_rows[1][1] == "MISS closed: expected allow, got hold"


def test_write_task_store_writes_one_file_per_task_under_the_case_claude_home(
    tmp_path: Path,
) -> None:
    task_case = {
        **CLOSED_CASE,
        "tasks": [{"id": "28", "subject": "Fix list reader", "status": "in_progress"}],
    }
    closing_round_run.write_task_store(task_case, tmp_path)
    task_file = tmp_path / "home" / ".claude" / "tasks" / "eval-session" / "28.json"
    assert json.loads(task_file.read_text(encoding="utf-8"))["status"] == "in_progress"
    closing_round_run.write_task_store(CLOSED_CASE, tmp_path / "other")
    assert not (tmp_path / "other").exists()


def test_case_environment_points_the_claude_home_into_the_case_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_TASK_LIST_ID", "caller-list")
    environment = closing_round_run.case_environment(CLOSED_CASE, tmp_path)
    assert environment["CLAUDE_CONFIG_DIR"] == str(tmp_path / "home" / ".claude")
    assert "CLAUDE_CODE_TASK_LIST_ID" not in environment


def test_case_decision_holds_work_beside_a_seeded_task_in_progress() -> None:
    work_case = {
        "id": "work",
        "expected": "hold",
        "transcript": [
            OPEN_ITEM_CASE["transcript"][0],
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_1", "name": "Edit", "input": {}}],
                },
            },
            CLOSED_CASE["transcript"][1],
        ],
    }
    assert closing_round_run.case_decision(work_case, closing_round_run.HOOK_FILE) == "allow"
    seeded_case = {
        **work_case,
        "tasks": [{"id": "28", "subject": "Fix list reader", "status": "in_progress"}],
    }
    assert closing_round_run.case_decision(seeded_case, closing_round_run.HOOK_FILE) == "hold"
