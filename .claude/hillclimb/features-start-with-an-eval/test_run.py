"""Behavior tests for eval run selection."""

import json
from pathlib import Path

import pytest

import run
from run import _append_line, _pending_runs, _read_rows, _run_one, _unscorable
from session_eval_support.config.constants import (
    FAILURE_NO_RESULT,
    MAX_TURNS_SUBTYPE,
    RESULTS_FILE_NAME,
    SUCCESS_SUBTYPE,
)
from session_eval_support.session import SessionRun, SessionSettings

SETTINGS = SessionSettings(
    model="claude-haiku", effort="low", max_turns=1, timeout_seconds=1
)


def _finished_session(subtype: str) -> SessionRun:
    result_event = {
        "type": "result",
        "subtype": subtype,
        "modelUsage": {"claude-haiku-5-5": {}},
    }
    return SessionRun([result_event], 0.0, 0, {})


def test_pending_runs_skip_completed_case_and_rep(tmp_path: Path) -> None:
    (tmp_path / RESULTS_FILE_NAME).write_text(
        json.dumps({"prompt_id": "case-a", "rep": 0}) + "\n"
    )
    cases = [{"id": "case-a"}, {"id": "case-b"}]

    assert _pending_runs(cases, 2, tmp_path) == [
        (cases[0], 1),
        (cases[1], 0),
        (cases[1], 1),
    ]


def test_success_and_turn_limit_sessions_are_scored() -> None:
    assert _unscorable(_finished_session(SUCCESS_SUBTYPE), SETTINGS) is None
    assert _unscorable(_finished_session(MAX_TURNS_SUBTYPE), SETTINGS) is None


def test_other_result_subtypes_are_unscorable() -> None:
    assert _unscorable(_finished_session("error_during_execution"), SETTINGS) == (
        FAILURE_NO_RESULT,
        "error_during_execution",
    )


def test_a_cut_off_results_line_is_skipped_and_the_next_row_starts_fresh(
    tmp_path: Path,
) -> None:
    results_path = tmp_path / RESULTS_FILE_NAME
    results_path.write_text(
        json.dumps({"prompt_id": "case-a", "rep": 0}) + "\n" + '{"prompt_id": "case-b'
    )

    _append_line(results_path, {"prompt_id": "case-b", "rep": 0})

    assert _pending_runs([{"id": "case-a"}, {"id": "case-b"}], 1, tmp_path) == []


def test_an_unreadable_results_line_is_logged_with_its_number(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    results_path = tmp_path / RESULTS_FILE_NAME
    results_path.write_text('{"prompt_id": "case-a", "rep": 0}\nnot json\n')

    assert _read_rows(results_path) == [{"prompt_id": "case-a", "rep": 0}]
    assert f"skipped unreadable line 2 of {results_path}" in caplog.text


def test_blank_results_lines_are_skipped_without_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    results_path = tmp_path / RESULTS_FILE_NAME
    results_path.write_text('{"prompt_id": "case-a", "rep": 0}\n\n')

    assert _read_rows(results_path) == [{"prompt_id": "case-a", "rep": 0}]
    assert "skipped" not in caplog.text


def test_run_one_deletes_the_workspace_when_the_session_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)
    monkeypatch.setattr(run, "prepare_workspace", lambda all_installs: workspace)

    def _fail(*all_arguments: object) -> SessionRun:
        raise RuntimeError("session crashed")

    monkeypatch.setattr(run, "run_session", _fail)

    with pytest.raises(RuntimeError):
        _run_one({"id": "case-a", "prompt": "ask"}, 0, tmp_path, [], SETTINGS)

    assert not workspace.exists()
