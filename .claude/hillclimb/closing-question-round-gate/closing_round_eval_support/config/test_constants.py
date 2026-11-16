"""Tests for the eval paths and the labels in the cases file."""

import json

from closing_round_eval_support.config.constants import (
    ALLOW_DECISION,
    CASE_EXPECTED_KEY,
    CASE_ID_KEY,
    CASES_FILE,
    HOLD_DECISION,
    HOOK_FILE,
    UTF8_ENCODING,
)


def test_flow_paths_point_at_files_in_the_checkout() -> None:
    assert CASES_FILE.is_file()
    assert HOOK_FILE.is_file()


def test_every_case_has_its_own_id_and_a_known_label() -> None:
    all_cases = json.loads(CASES_FILE.read_text(encoding=UTF8_ENCODING))
    all_case_ids = [each_case[CASE_ID_KEY] for each_case in all_cases]
    assert len(all_case_ids) == len(set(all_case_ids))
    assert {each_case[CASE_EXPECTED_KEY] for each_case in all_cases} == {
        HOLD_DECISION,
        ALLOW_DECISION,
    }
