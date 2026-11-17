"""Behavioral tests for starting, holding and stopping the gate's child processes."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import gate_child_process
from blocking.gate_child_process import close_job, job_holding, started_child, stop_child

SLEEPING_CHILD = [sys.executable, "-c", "import time; time.sleep(30)"]
PRINTING_CHILD = [sys.executable, "-c", "print('answer')"]
FAKE_JOB_HANDLE = 7


def test_started_child_should_pipe_the_output_of_a_child_that_starts() -> None:
    child = started_child(PRINTING_CHILD, None, None)
    assert child is not None
    assert child.communicate(timeout=10)[0] == "answer\n"


def test_started_child_should_take_input_when_asked() -> None:
    child = started_child([sys.executable, "-c", "import sys; print(sys.stdin.read())"], None, None, True)
    assert child is not None
    assert child.communicate(input="given", timeout=10)[0] == "given\n"


def test_started_child_should_return_none_for_a_program_that_cannot_start(tmp_path: Path) -> None:
    assert started_child([str(tmp_path / "no-such-program")], None, None) is None


def test_job_holding_should_give_no_job_outside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate_child_process.sys, "platform", "linux")
    child = started_child(PRINTING_CHILD, None, None)
    assert child is not None
    child.communicate(timeout=10)
    assert job_holding(child) is None


def test_stop_child_should_end_a_child_that_still_runs() -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX process groups")
    child = started_child(SLEEPING_CHILD, None, None)
    assert child is not None
    stop_child(child, None)
    assert child.poll() == -signal.SIGKILL


def test_close_job_should_close_nothing_without_a_job() -> None:
    assert close_job(None) is False


def test_close_job_should_close_the_job_handle_it_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    all_closed: list[int] = []

    class FakeKernel32:
        def CloseHandle(self, job: int) -> int:
            all_closed.append(job)
            return 1

    monkeypatch.setattr(gate_child_process, "_kernel32", FakeKernel32)
    assert close_job(FAKE_JOB_HANDLE) is True
    assert all_closed == [FAKE_JOB_HANDLE]
