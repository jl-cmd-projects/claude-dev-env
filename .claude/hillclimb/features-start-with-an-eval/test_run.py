"""Behavior tests for eval run selection."""

import json
from pathlib import Path

from run import _pending_runs, _unscorable
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
