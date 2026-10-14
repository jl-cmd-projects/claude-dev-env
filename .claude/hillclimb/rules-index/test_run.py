import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parent
sys.path[:0] = [
    str(flow_directory),
    str(flow_directory.parent / "features-start-with-an-eval"),
    str(flow_directory.parents[2] / "packages" / "claude-dev-env" / "scripts"),
]

from run import _summary
from session_eval_support.rows import append_row, read_rows, select_cases
from session_eval_support.session import SessionRun, SessionSettings, unscorable


def test_unscorable_reports_a_broker_wait_before_examining_events() -> None:
    session = SessionRun([], 0.0, 3, {"final_decision": "wait"})
    settings = SessionSettings("model", "low", 1, 10)

    assert unscorable(session, settings) == ("broker-wait", "wait")


def test_summary_counts_passes_and_errors() -> None:
    rows = [
        {"tags": ["group", "rule"], "grade": {"followed": 1, "opened_guide": 1}},
        {"tags": ["group", "rule"], "grade": {"followed": 0, "opened_guide": 0}},
    ]

    summary = _summary(rows, 1)

    assert "followed 1/2" in summary
    assert "group 1/2" in summary
    assert "opened a guide 1/2" in summary
    assert "errors 1" in summary


def test_rows_survive_a_partial_line_left_by_a_killed_run(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    results.write_text('{"prompt_id": "w02", "rep": 0}\n{"prompt_id": "b02", "re', encoding="utf-8")

    assert read_rows(results) == [{"prompt_id": "w02", "rep": 0}]

    append_row(results, {"prompt_id": "s01", "rep": 0})

    assert read_rows(results) == [{"prompt_id": "w02", "rep": 0}, {"prompt_id": "s01", "rep": 0}]


def test_select_cases_refuses_an_unknown_id_and_keeps_file_order() -> None:
    all_cases = [{"id": "w02"}, {"id": "b02"}, {"id": "s01"}]

    assert select_cases(all_cases, "s01,w02") == [{"id": "w02"}, {"id": "s01"}]
    assert select_cases(all_cases, "") == all_cases
    with pytest.raises(ValueError, match="b02x"):
        select_cases(all_cases, "w02,b02x")
