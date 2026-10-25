"""Tests for the scope-boundary results row."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
for each_root in (
    flow_directory,
    flow_directory.parent / "features-start-with-an-eval",
):
    if str(each_root) not in sys.path:
        sys.path.insert(0, str(each_root))

from scope_eval_support.scoring import scored_row
from session_eval_support.session import SessionRun, SessionSettings

CASE = {"id": "d01", "prompt": "Port it.", "group": "drift", "source": "thread"}
SETTINGS = SessionSettings("claude-opus-5-5", "medium", 20, 900)


def test_scored_row_should_carry_the_case_id_and_the_given_meta() -> None:
    session_run = SessionRun([], 1.0, 0, {})
    row_by_field = scored_row(
        CASE, 0, session_run, SETTINGS, {"correct": 1}, {"edited_paths": ["a.py"]}
    )
    assert (row_by_field["prompt_id"], row_by_field["meta"]["edited_paths"]) == (
        "d01",
        ["a.py"],
    )
