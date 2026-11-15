import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import closing_question_round_gate

from hooks_constants.closing_question_round_gate_constants import (
    MAXIMUM_PAYLOAD_BYTES,
    WORK_REASON_LEAD,
)
from test_closing_question_round_gate import (
    held_reason,
    reply_record,
    stop_feedback_record,
    tool_call_record,
    tool_result_record,
    typed_prompt_record,
    write_records,
)
from test_closing_question_round_gate_work import (
    DECLARATION,
    WORK_FEEDBACK_TEXT,
    edit_records,
)

GATE_PATH = Path(__file__).resolve().parent / "closing_question_round_gate.py"


@pytest.mark.parametrize(
    "closing_reply",
    [f"Done.\n\n* {DECLARATION}", f"Done.\n\n* **{DECLARATION}**", "Done.\n\nOpen_ items: none."],
)
def test_should_hold_a_declaration_in_a_star_list_item_or_with_a_stray_mark(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_not_count_a_hand_back_that_quotes_the_reason_as_a_hold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    hand_back = stop_feedback_record(f"A worker reports. It quotes this: {WORK_REASON_LEAD}")
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        hand_back,
        reply_record("Done."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_not_count_a_typed_prompt_that_quotes_the_feedback_as_a_hold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    typed_quote = typed_prompt_record()
    message_body = typed_quote["message"]
    assert isinstance(message_body, dict)
    message_body["content"] = WORK_FEEDBACK_TEXT
    all_records = [
        typed_prompt_record(),
        typed_quote,
        typed_quote,
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


@pytest.mark.parametrize("closing_payload", [{}, {"last_assistant_message": ""}])
def test_should_hold_work_after_an_earlier_declaration_when_no_closing_text_follows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_payload: dict[str, object],
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{DECLARATION}"),
        typed_prompt_record(),
        *edit_records(),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records, closing_payload)
    assert str(reason).startswith(WORK_REASON_LEAD)


def test_should_hold_a_tool_call_that_shares_a_record_with_the_declaration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    declared_call = tool_call_record("Edit", {"file_path": "jobs/export.py"}, tool_use_id="id-x")
    message_body = declared_call["message"]
    assert isinstance(message_body, dict)
    message_body["content"] = [{"type": "text", "text": DECLARATION}, *message_body["content"]]
    all_records = [
        typed_prompt_record(),
        declared_call,
        tool_result_record("Edit", "The file was updated.", tool_use_id="id-x"),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": ""})
    assert str(reason).startswith(WORK_REASON_LEAD)


def test_should_allow_a_declaration_the_payload_carries_after_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), *edit_records()]
    closing_payload: dict[str, object] = {"last_assistant_message": f"Done.\n\n{DECLARATION}"}
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, closing_payload) is None


def test_should_allow_a_payload_declaration_that_repeats_a_text_from_before_the_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), reply_record(DECLARATION), *edit_records()]
    closing_payload: dict[str, object] = {"last_assistant_message": DECLARATION}
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, closing_payload) is None


@pytest.mark.parametrize(
    "closing_reply",
    [f"**{DECLARATION}", f"{DECLARATION}__", f"**{DECLARATION}_"],
)
def test_should_hold_a_declaration_with_unmatched_marks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_allow_within_ten_seconds_when_a_scan_step_never_reads_the_clock(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    all_pending_calls = [
        tool_call_record("AskUserQuestion", tool_use_id=f"id-{each_number}")
        for each_number in range(20000)
    ]
    oversized_result = tool_result_record("Read", "z" * (15 * 1024 * 1024), tool_use_id="id-none")
    write_records(transcript_path, [typed_prompt_record(), *all_pending_calls, oversized_result])
    hook_input = {"hook_event_name": "Stop", "transcript_path": str(transcript_path)}
    started_at = time.monotonic()
    completed_gate = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HOME": str(tmp_path), "CLAUDE_CODE_SESSION_ATTENDED": "1"},
    )
    assert completed_gate.returncode in (0, 2)
    assert time.monotonic() - started_at < 10


def test_watchdog_should_not_exit_once_the_hold_output_has_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_exit_codes: list[int] = []
    monkeypatch.setattr(closing_question_round_gate.os, "_exit", all_exit_codes.append)
    output_lock = threading.Lock()
    output_lock.acquire()
    closing_question_round_gate._allow_now(output_lock)
    assert all_exit_codes == []


def test_watchdog_should_exit_with_allow_before_any_hold_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_exit_codes: list[int] = []
    monkeypatch.setattr(closing_question_round_gate.os, "_exit", all_exit_codes.append)
    closing_question_round_gate._allow_now(threading.Lock())
    assert all_exit_codes == [0]


def test_should_allow_a_payload_over_the_payload_cap_without_parsing_it(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    write_records(transcript_path, [typed_prompt_record(), *edit_records(), reply_record("Done.")])
    hook_input = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript_path),
        "last_assistant_message": "Done.",
        "padding": "z" * (MAXIMUM_PAYLOAD_BYTES + 1),
    }
    completed_gate = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HOME": str(tmp_path), "CLAUDE_CODE_SESSION_ATTENDED": "1"},
    )
    assert (completed_gate.returncode, completed_gate.stdout) == (0, "")


def test_should_hold_a_payload_under_the_payload_cap(tmp_path: Path) -> None:
    transcript_path = tmp_path / "s.jsonl"
    write_records(transcript_path, [typed_prompt_record(), *edit_records(), reply_record("Done.")])
    hook_input = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript_path),
        "last_assistant_message": "Done.",
    }
    completed_gate = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input="\ufeff" + json.dumps(hook_input),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HOME": str(tmp_path), "CLAUDE_CODE_SESSION_ATTENDED": "1"},
    )
    assert completed_gate.returncode == 2


def test_should_allow_within_ten_seconds_when_one_parse_holds_the_interpreter(
    tmp_path: Path,
) -> None:
    line_budget = 16 * 1024 * 1024 - 200
    nested_unit = "[" * 500 + "0" + "]" * 500 + ","
    nested_items = (nested_unit * (line_budget // len(nested_unit)))[:-1]
    heavy_line = '{"type":"assistant","turnOrigin":"human","a":[' + nested_items + "]}\n"
    prompt_line = (
        json.dumps({"type": "user", "turnOrigin": "human", "message": {"role": "user", "content": "Go."}})
        + "\n"
    )
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text(prompt_line + heavy_line * 3, encoding="utf-8")
    hook_input = {"transcript_path": str(transcript_path), "last_assistant_message": "Done."}
    unattended_environment = {**os.environ, "HOME": str(tmp_path)}
    unattended_environment.pop("CLAUDE_CODE_SESSION_ATTENDED", None)
    started_at = time.monotonic()
    completed_gate = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        check=False,
        env=unattended_environment,
    )
    assert completed_gate.returncode in (0, 2)
    assert time.monotonic() - started_at < 10


def test_supervised_main_should_allow_with_no_output_when_the_decision_times_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def timed_out_run(*all_arguments: object, **all_options: object) -> object:
        raise subprocess.TimeoutExpired(cmd="gate", timeout=1)

    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    monkeypatch.setattr(closing_question_round_gate.subprocess, "run", timed_out_run)
    assert closing_question_round_gate.supervised_main() == 0
    assert capsys.readouterr().out == ""


def test_supervised_main_should_relay_the_decision_output_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def held_run(*all_arguments: object, **all_options: object) -> object:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout=b'{"x": 1}', stderr=b"why")

    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    monkeypatch.setattr(closing_question_round_gate.subprocess, "run", held_run)
    assert closing_question_round_gate.supervised_main() == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ('{"x": 1}', "why")


def test_supervised_main_should_allow_when_the_output_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def held_run(*all_arguments: object, **all_options: object) -> object:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout=b'{"x": 1}', stderr=b"why")

    class ClosedStream:
        buffer = io.BufferedWriter(io.BytesIO())

        def __init__(self) -> None:
            self.buffer.close()

    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    monkeypatch.setattr("sys.stdout", ClosedStream())
    monkeypatch.setattr(closing_question_round_gate.subprocess, "run", held_run)
    assert closing_question_round_gate.supervised_main() == 0
