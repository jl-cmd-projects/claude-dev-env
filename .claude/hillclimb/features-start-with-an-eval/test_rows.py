import sys
from pathlib import Path

import pytest

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.rows import (
    append_row,
    failure_row,
    read_rows,
    rows_for_install,
    select_cases,
    select_variant,
)


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
    assert select_cases(all_cases, " w02 , s01 ") == [{"id": "w02"}, {"id": "s01"}]
    with pytest.raises(ValueError, match="b02x, b03x"):
        select_cases(all_cases, "w02,b03x,b02x")


def test_rows_for_install_keeps_rows_of_the_digest_and_the_selected_cases(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    all_rows = [
        {"prompt_id": "w02", "rep": 0, "meta": {"installed_digest": "aaa"}},
        {"prompt_id": "w02", "rep": 1, "meta": {"installed_digest": "bbb"}},
        {"prompt_id": "b02", "rep": 0, "meta": {"installed_digest": "aaa"}},
        {"prompt_id": "s01", "rep": 0},
    ]
    for each_row in all_rows:
        append_row(results, each_row)

    assert rows_for_install(results, "aaa", {"w02", "s01"}) == all_rows[:1]


def test_select_variant_refuses_an_unknown_name() -> None:
    variant_by_name = {"baseline": {"ref": "abc"}, "index": {"ref": "HEAD"}}

    assert select_variant(variant_by_name, "index") == {"ref": "HEAD"}
    with pytest.raises(ValueError, match="unknown variant: indx"):
        select_variant(variant_by_name, "indx")


def test_failure_row_tags_the_digest_so_rows_for_install_counts_it(tmp_path: Path) -> None:
    errors = tmp_path / "errors.jsonl"
    row = failure_row({"id": "w02", "prompt": "ask"}, 1, "aaa", "timeout", 600)
    append_row(errors, row)

    assert row == {"prompt_id": "w02", "rep": 1, "failure_class": "timeout", "detail": 600, "meta": {"installed_digest": "aaa"}}
    assert rows_for_install(errors, "aaa", {"w02"}) == [row]
