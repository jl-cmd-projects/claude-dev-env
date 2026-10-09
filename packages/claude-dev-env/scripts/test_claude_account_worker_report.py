from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_account_worker_report import (
    WorkerReport,
    finalize_report,
    make_report,
    pre_launch_failure_report,
    wait_report,
    write_report,
)
from dev_env_scripts_constants.account_broker_constants import WAIT_EXIT_CODE
from dev_env_scripts_constants.claude_account_worker_constants import (
    STDOUT_TAIL_CHARACTER_LIMIT,
)


def test_should_build_wait_report_with_wait_exit_code_and_reset_time() -> None:
    reset_at = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)

    report = wait_report("wait", "no account has room", reset_at)

    assert report == WorkerReport(
        account="wait",
        reason="no account has room",
        exit_code=WAIT_EXIT_CODE,
        duration_seconds=0.0,
        payload=None,
        is_error=False,
        wait_reset_at=reset_at,
    )


def test_should_build_report_from_json_result_and_round_duration() -> None:
    report = make_report(
        "extra_2",
        "served",
        exit_code=0,
        duration_seconds=1.23456,
        stdout_text='{"result":"ready","is_error":false}',
    )

    assert report.payload == "ready"
    assert report.is_error is False
    assert report.duration_seconds == 1.235
    assert report.wait_reset_at is None


def test_should_take_the_result_event_from_streamed_output() -> None:
    streamed_lines = "\n".join(
        (
            '{"type":"system","subtype":"init","session_id":"s1"}',
            '{"type":"assistant","message":{"content":[]}}',
            '{"type":"result","result":"ready","is_error":false}',
        )
    )

    report = make_report("extra_2", "served", exit_code=0, duration_seconds=1.0, stdout_text=streamed_lines)

    assert report.payload == "ready"
    assert report.is_error is False


def test_should_mark_report_as_error_when_json_flags_error() -> None:
    report = make_report(
        "extra_2",
        "served",
        exit_code=0,
        duration_seconds=0.0,
        stdout_text='{"result":"failed","is_error":true}',
    )

    assert report.payload == "failed"
    assert report.is_error is True


def test_should_mark_report_as_error_when_exit_code_is_nonzero() -> None:
    report = make_report(
        "extra_2",
        "served",
        exit_code=5,
        duration_seconds=0.0,
        stdout_text='{"result":"ready","is_error":false}',
    )

    assert report.exit_code == 5
    assert report.is_error is True


def test_should_keep_bounded_stdout_tail_when_stdout_is_not_json() -> None:
    stdout_text = "x" * STDOUT_TAIL_CHARACTER_LIMIT + "tail"

    report = make_report(
        "extra_2", "served", exit_code=0, duration_seconds=0.0, stdout_text=stdout_text
    )

    assert report.payload == stdout_text[-STDOUT_TAIL_CHARACTER_LIMIT:]
    assert len(report.payload) == STDOUT_TAIL_CHARACTER_LIMIT
    assert report.is_error is True


def test_should_drop_payload_when_json_has_no_result_key() -> None:
    report = make_report(
        "extra_2",
        "served",
        exit_code=0,
        duration_seconds=0.0,
        stdout_text='{"other":1}',
    )

    assert report.payload is None
    assert report.is_error is True


def test_should_build_pre_launch_failure_report_with_zero_duration() -> None:
    report = pre_launch_failure_report("none", "prompt file is unreadable", 1)

    assert report.account == "none"
    assert report.reason == "prompt file is unreadable"
    assert report.exit_code == 1
    assert report.duration_seconds == 0.0
    assert report.is_error is True
    assert report.wait_reset_at is None


def test_should_write_report_as_json_and_create_parent_directory(
    tmp_path: Path,
) -> None:
    reset_at = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    report_file = tmp_path / "nested" / "report.json"

    write_report(report_file, wait_report("wait", "no account has room", reset_at))

    report_text = report_file.read_text(encoding="utf-8")
    assert report_text.endswith("\n")
    assert json.loads(report_text) == {
        "account": "wait",
        "reason": "no account has room",
        "exit_code": WAIT_EXIT_CODE,
        "duration_seconds": 0.0,
        "result": None,
        "is_error": False,
        "wait_reset_at": reset_at.isoformat(),
    }


def test_should_finalize_report_by_writing_it_printing_summary_and_returning_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_file = tmp_path / "report.json"
    report = make_report(
        "extra_2",
        "served",
        exit_code=4,
        duration_seconds=2.0,
        stdout_text='{"result":"done","is_error":false}',
    )

    exit_code = finalize_report(report_file, report)

    assert exit_code == 4
    written_report = json.loads(report_file.read_text(encoding="utf-8"))
    assert written_report["result"] == "done"
    assert written_report["wait_reset_at"] is None
    assert (
        capsys.readouterr().out == f"account=extra_2 exit_code=4 report={report_file}\n"
    )
