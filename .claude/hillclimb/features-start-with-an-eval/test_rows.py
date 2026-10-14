import sys
from pathlib import Path

import pytest

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.rows import append_row, read_rows, select_cases


def test_rows_survive_a_partial_line_left_by_a_killed_run(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    results.write_text('{"prompt_id": "w02", "rep": 0}\n{"prompt_id": "b02", "re', encoding="utf-8")

    assert read_rows(results) == [{"prompt_id": "w02", "rep": 0}]

    append_row(results, {"prompt_id": "s01", "rep": 0})

    assert read_rows(results) == [{"prompt_id": "w02", "rep": 0}, {"prompt_id": "s01", "rep": 0}]


def test_read_rows_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_rows(tmp_path / "missing.jsonl") == []


def test_select_cases_refuses_an_unknown_id_and_keeps_file_order() -> None:
    all_cases = [{"id": "w02"}, {"id": "b02"}, {"id": "s01"}]

    assert select_cases(all_cases, "s01,w02") == [{"id": "w02"}, {"id": "s01"}]
    assert select_cases(all_cases, "") == all_cases
    with pytest.raises(ValueError, match="b02x, b03x"):
        select_cases(all_cases, "w02,b03x,b02x")
