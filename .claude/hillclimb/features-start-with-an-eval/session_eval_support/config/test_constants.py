"""Tests for the eval paths."""

from session_eval_support.config.constants import (
    CASES_FILE,
    FIXTURE_DIRECTORY,
    STATE_FILE,
)


def test_flow_paths_point_at_files_in_the_checkout() -> None:
    assert CASES_FILE.is_file()
    assert STATE_FILE.is_file()
    assert FIXTURE_DIRECTORY.is_dir()
