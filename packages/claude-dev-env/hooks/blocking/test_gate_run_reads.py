"""Behavior tests for the answers one pull request lifecycle gate run remembers."""

import sys
import time
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import gate_run_reads
from blocking.gate_run_reads import (
    ReadSlice,
    answer_once,
    answer_within_allowance,
    child_stdout,
    gate_run,
    read_allowance,
    read_deadlines_started,
)
from hooks_constants.gate_run_reads_constants import (
    FOLLOWUP_READS_SECONDS,
    KILL_GRACE_SECONDS,
    PROOF_AND_LOOK_READS_SECONDS,
)

CLOCK_START = 100.0
HIDDEN_WINDOW_FLAGS = 0x08000000
SLEEP_THEN_PRINT = "import time; time.sleep(30); print('late')"
GRANDCHILD_HOLDS_THE_PIPE = (
    "import subprocess, sys, time;"
    " subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
    " time.sleep(30)"
)
ELAPSED_SLACK_SECONDS = 8.0


class FakeClock:
    def __init__(self) -> None:
        self.now = CLOCK_START

    def __call__(self) -> float:
        return self.now


def _counting_read(all_reads: list[str], answer: str | None):
    def read() -> str | None:
        all_reads.append("read")
        return answer

    return read


def test_answer_once_should_read_a_question_once_inside_one_run() -> None:
    all_reads: list[str] = []
    with gate_run():
        assert (
            answer_once(("origin", "/repo"), _counting_read(all_reads, "owner/name"))
            == "owner/name"
        )
        assert (
            answer_once(("origin", "/repo"), _counting_read(all_reads, "other/name"))
            == "owner/name"
        )
    assert all_reads == ["read"]


def test_answer_once_should_remember_an_unanswered_read() -> None:
    all_reads: list[str] = []
    with gate_run():
        assert answer_once(("origin", "/repo"), _counting_read(all_reads, None)) is None
        assert answer_once(("origin", "/repo"), _counting_read(all_reads, "owner/name")) is None
    assert all_reads == ["read"]


def test_answer_once_should_read_each_time_with_no_run_open() -> None:
    all_reads: list[str] = []
    assert answer_once(("origin", "/repo"), _counting_read(all_reads, "a")) == "a"
    assert answer_once(("origin", "/repo"), _counting_read(all_reads, "b")) == "b"
    assert all_reads == ["read", "read"]


def test_gate_run_should_forget_its_answers_when_it_closes() -> None:
    all_reads: list[str] = []
    with gate_run() as first_run:
        answer_once(("origin", "/repo"), _counting_read(all_reads, "a"))
    with gate_run():
        assert answer_once(("origin", "/repo"), _counting_read(all_reads, "b")) == "b"
    assert first_run.answer_by_question == {("origin", "/repo"): "a"}
    assert all_reads == ["read", "read"]


def test_read_allowance_should_keep_the_own_timeout_with_no_deadline_started() -> None:
    assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) == 5
    assert read_allowance(4, ReadSlice.FOLLOWUP) == 4


def test_read_allowance_should_take_the_smaller_of_the_own_timeout_and_the_time_left() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock):
        assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) == 5
        clock.now = CLOCK_START + 9
        assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) == 3
        clock.now = CLOCK_START + 18
        assert read_allowance(4, ReadSlice.FOLLOWUP) == 2
    assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) == 5


def test_read_allowance_should_keep_the_reserved_slice_for_followup_reads() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock):
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS - 0.5
        assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) == 0.5
        assert read_allowance(4, ReadSlice.FOLLOWUP) == 4
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS
        assert read_allowance(5, ReadSlice.PROOF_AND_LOOK) is None
        assert read_allowance(4, ReadSlice.FOLLOWUP) == 4
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS + FOLLOWUP_READS_SECONDS
        assert read_allowance(4, ReadSlice.FOLLOWUP) is None


def test_child_stdout_should_skip_a_read_with_no_time_left(tmp_path: Path) -> None:
    marker_path = tmp_path / "ran.txt"
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS
        command = [sys.executable, "-c", f"open({str(marker_path)!r}, 'w').write('x')"]
        assert child_stdout(command, 5, ReadSlice.PROOF_AND_LOOK) is None
    assert not marker_path.exists()
    assert run.was_read_cut_short


def test_child_stdout_should_return_the_output_of_a_child_that_answers() -> None:
    with gate_run() as run:
        assert child_stdout([sys.executable, "-c", "print('answer')"], 5, ReadSlice.PROOF_AND_LOOK) == "answer\n"
        assert child_stdout([sys.executable, "-c", "raise SystemExit(3)"], 5, ReadSlice.PROOF_AND_LOOK) is None
    assert not run.was_read_cut_short


def test_child_stdout_should_start_its_child_with_the_hidden_window_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    all_seen_flags: list[object] = []

    def refuse_to_start(*all_arguments: object, **all_options: object) -> None:
        all_seen_flags.append(all_options.get("creationflags"))
        raise OSError("this test starts no child")

    monkeypatch.setattr(gate_run_reads, "hidden_window_creation_flags", lambda: HIDDEN_WINDOW_FLAGS)
    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", refuse_to_start)
    assert child_stdout(["git", "status"], 5, ReadSlice.PROOF_AND_LOOK) is None
    assert all_seen_flags == [HIDDEN_WINDOW_FLAGS]


def test_child_stdout_should_kill_a_child_that_outlives_its_own_timeout() -> None:
    with gate_run() as run:
        started = time.monotonic()
        assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 0.5, ReadSlice.PROOF_AND_LOOK) is None
        elapsed = time.monotonic() - started
    assert elapsed < 0.5 + ELAPSED_SLACK_SECONDS
    assert not run.was_read_cut_short


def test_child_stdout_should_stop_waiting_when_a_grandchild_holds_the_pipe() -> None:
    started = time.monotonic()
    assert child_stdout([sys.executable, "-c", GRANDCHILD_HOLDS_THE_PIPE], 0.5, ReadSlice.PROOF_AND_LOOK) is None
    assert time.monotonic() - started < 0.5 + KILL_GRACE_SECONDS + ELAPSED_SLACK_SECONDS


def test_child_stdout_should_mark_the_run_when_the_deadline_cuts_a_read_short() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS - 0.4
        started = time.monotonic()
        assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 5, ReadSlice.PROOF_AND_LOOK) is None
        elapsed = time.monotonic() - started
    assert elapsed < 0.4 + ELAPSED_SLACK_SECONDS
    assert run.was_read_cut_short


def _slow_read(allowance: float) -> list[str]:
    time.sleep(allowance + 30)
    return ["late"]


def test_answer_within_allowance_should_bound_the_whole_read() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS + FOLLOWUP_READS_SECONDS - 0.3
        started = time.monotonic()
        answer = answer_within_allowance(_slow_read, 4, ReadSlice.FOLLOWUP)
        elapsed = time.monotonic() - started
    assert answer is None
    assert elapsed < 0.3 + ELAPSED_SLACK_SECONDS
    assert run.was_read_cut_short


def test_answer_within_allowance_should_return_the_answer_and_raise_the_read_error() -> None:
    all_allowances: list[float] = []

    def answering_read(allowance: float) -> list[str]:
        all_allowances.append(allowance)
        return ["ok"]

    def failing_read(allowance: float) -> list[str]:
        raise OSError("offline")

    assert answer_within_allowance(answering_read, 4, ReadSlice.FOLLOWUP) == ["ok"]
    assert all_allowances == [4]
    with pytest.raises(OSError, match="offline"):
        answer_within_allowance(failing_read, 4, ReadSlice.FOLLOWUP)
