"""Tests for eval paths and scorable session outcomes."""

import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parents[2])
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.config.constants import (
    ALL_SCORABLE_SUBTYPES,
    CASES_FILE,
    FLOW_ROOT,
    MAX_TURNS_SUBTYPE,
    SUCCESS_SUBTYPE,
)


def test_cases_file_belongs_to_flow_root() -> None:
    assert CASES_FILE == FLOW_ROOT / "cases.json"
    assert CASES_FILE.is_file()


def test_success_and_turn_limit_are_scorable() -> None:
    assert ALL_SCORABLE_SUBTYPES == {SUCCESS_SUBTYPE, MAX_TURNS_SUBTYPE}
