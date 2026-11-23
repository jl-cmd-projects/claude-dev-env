from pathlib import Path

from hooks_constants.closing_question_round_gate_constants import STOP_DEADLINE_SECONDS, WATCHDOG_GRACE_SECONDS
from hooks_constants.open_tasks_stop_gate_constants import (
    CLOSING_ROUND_GATE_FILE_NAME,
    CLOSING_ROUND_START_ALLOWANCE_SECONDS,
    REASON_SEPARATOR,
)

OPEN_TASKS_HOOK_TIMEOUT_SECONDS = 45


def test_closing_round_gate_file_name_should_name_a_script_in_the_blocking_directory() -> None:
    blocking_directory = Path(__file__).resolve().parent.parent / "blocking"
    assert (blocking_directory / CLOSING_ROUND_GATE_FILE_NAME).is_file()


def test_closing_round_run_should_end_inside_the_open_tasks_hook_timeout() -> None:
    round_run_seconds = STOP_DEADLINE_SECONDS + WATCHDOG_GRACE_SECONDS + CLOSING_ROUND_START_ALLOWANCE_SECONDS
    assert round_run_seconds < OPEN_TASKS_HOOK_TIMEOUT_SECONDS


def test_reason_separator_should_put_a_blank_line_between_two_reasons() -> None:
    assert REASON_SEPARATOR.join(["first", "second"]) == "first\n\nsecond"
