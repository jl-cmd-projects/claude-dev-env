"""Behavior tests for the answers one pull request lifecycle gate run remembers."""

import ast
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
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
    lines_within_slice,
    read_allowance,
    read_deadlines_started,
    transcript_lines_within_slice,
)
from hooks_constants.followup_pr_dedupe_constants import READ_TIMEOUT_SECONDS
from hooks_constants.gate_run_reads_constants import (
    FOLLOWUP_READS_SECONDS,
    KILL_GRACE_SECONDS,
    MOST_CUT_READS_PER_RUN,
    PROOF_AND_LOOK_READS_SECONDS,
    STARTUP_AND_OUTPUT_MARGIN_SECONDS,
    PROCESS_HANDLE_ATTRIBUTE,
    STOPPED_JOB_EXIT_CODE,
)

CLOCK_START = 100.0
OLDEST_SUPPORTED_PYTHON = (3, 11)
HIDDEN_WINDOW_FLAGS = 0x08000000
SLEEP_THEN_PRINT = "import time; time.sleep(30); print('late')"
HELD_READ_GIVES_UP_SECONDS = 30
GRANDCHILD_WAITS_FOR_RELEASE = (
    "import os, sys, time\n"
    "gave_up_path, release_path = sys.argv[1], sys.argv[2]\n"
    "polls_left = 300\n"
    "while polls_left and not os.path.exists(release_path):\n"
    "    time.sleep(0.1)\n"
    "    polls_left -= 1\n"
    "if not os.path.exists(release_path):\n"
    "    open(gave_up_path, 'w').close()\n"
)
CHILD_STARTS_A_GRANDCHILD = (
    "import subprocess, sys, time;"
    " subprocess.Popen([sys.executable, '-c', *sys.argv[1:]]);"
    " time.sleep(30)"
)
GATE_COMMAND_SUFFIX = "hooks/blocking/pr_lifecycle_" + "skill_gate.py"
CHILD_STARTS_A_SLEEPING_GRANDCHILD = (
    "import subprocess, sys, time;"
    " subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]);"
    " time.sleep(60)"
)
GRANDCHILD_WRITES_ITS_PID_AND_SLEEPS = (
    "import os, sys, time;"
    " open(sys.argv[1] + '.part', 'w').write(str(os.getpid()));"
    " os.replace(sys.argv[1] + '.part', sys.argv[1]);"
    " time.sleep(60)"
)
GRANDCHILD_READ_TIMEOUT_SECONDS = 3
GRANDCHILD_PID_WAIT_SECONDS = 5
GRANDCHILD_GONE_WITHIN_SECONDS = 2
WINDOWS_STOP_SLACK_SECONDS = 0.5
CHILD_STARTS_A_GRANDCHILD_AND_EXITS = (
    "import subprocess, sys;"
    " subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])"
)
FAKE_JOB_HANDLE = 4242
FAKE_PROCESS_HANDLE = 777
HUGE_LINE_BYTES = 1000
SECONDS_LEFT_BEFORE_HUGE_LINE = 5


class FakeClock:
    def __init__(self) -> None:
        self.now = CLOCK_START

    def __call__(self) -> float:
        return self.now


class RecordedChild(subprocess.Popen[str]):
    """A child that notes the timeout of each wait its caller makes."""

    def __init__(self, *all_arguments: object, **all_options: object) -> None:
        self.all_wait_timeouts: list[object] = []
        super().__init__(*all_arguments, **all_options)

    def communicate(self, *all_arguments: object, **all_options: object) -> tuple[str, str]:
        self.all_wait_timeouts.append(all_options.get("timeout"))
        return super().communicate(*all_arguments, **all_options)


@pytest.fixture
def all_started_children(monkeypatch: pytest.MonkeyPatch) -> list[RecordedChild]:
    all_children: list[RecordedChild] = []

    def start(*all_arguments: object, **all_options: object) -> RecordedChild:
        child = RecordedChild(*all_arguments, **all_options)
        all_children.append(child)
        return child

    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", start)
    return all_children


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


def test_child_stdout_should_start_its_child_with_the_environment_it_is_given() -> None:
    read_variable = [sys.executable, "-c", "import os; print(os.environ.get('GATE_READ_PROBE', 'unset'))"]
    environment = {**os.environ, "GATE_READ_PROBE": "given"}
    with gate_run():
        assert child_stdout(read_variable, 5, ReadSlice.PROOF_AND_LOOK, None, environment) == "given\n"
        assert child_stdout(read_variable, 5, ReadSlice.PROOF_AND_LOOK) == "unset\n"


def test_child_stdout_should_start_its_child_with_the_hidden_window_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    all_seen_flags: list[object] = []

    def refuse_to_start(*all_arguments: object, **all_options: object) -> None:
        all_seen_flags.append(all_options.get("creationflags"))
        raise OSError("this test starts no child")

    monkeypatch.setattr(gate_run_reads, "hidden_window_creation_flags", lambda: HIDDEN_WINDOW_FLAGS)
    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", refuse_to_start)
    assert child_stdout(["git", "status"], 5, ReadSlice.PROOF_AND_LOOK) is None
    assert all_seen_flags == [HIDDEN_WINDOW_FLAGS]


def test_child_stdout_should_kill_a_child_that_outlives_its_own_timeout(
    all_started_children: list[RecordedChild],
) -> None:
    with gate_run() as run:
        assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 0.5, ReadSlice.PROOF_AND_LOOK) is None
    (child,) = all_started_children
    assert child.all_wait_timeouts == [0.5, KILL_GRACE_SECONDS]
    assert child.wait() != 0
    assert not run.was_read_cut_short


def test_child_stdout_should_count_a_read_stopped_at_its_own_timeout() -> None:
    with gate_run() as run:
        assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 0.5, ReadSlice.PROOF_AND_LOOK) is None
    assert run.timed_out_read_count == 1
    assert not run.was_read_cut_short


def test_child_stdout_should_not_count_a_fast_failing_child_as_timed_out() -> None:
    with gate_run() as run:
        assert child_stdout([sys.executable, "-c", "raise SystemExit(3)"], 5, ReadSlice.PROOF_AND_LOOK) is None
    assert run.timed_out_read_count == 0


def test_child_stdout_should_stop_waiting_when_a_grandchild_holds_the_pipe(tmp_path: Path) -> None:
    gave_up_path = tmp_path / "gave-up"
    release_path = tmp_path / "release"
    command = [
        sys.executable,
        "-c",
        CHILD_STARTS_A_GRANDCHILD,
        GRANDCHILD_WAITS_FOR_RELEASE,
        str(gave_up_path),
        str(release_path),
    ]
    answer = child_stdout(command, 1, ReadSlice.PROOF_AND_LOOK)
    release_path.touch()
    assert answer is None
    assert not gave_up_path.exists()


def _is_running(process_id: int) -> bool:
    stat_path = Path(f"/proc/{process_id}/stat")
    if stat_path.parent.parent.is_dir():
        try:
            stat_text = stat_path.read_text(encoding="ascii", errors="replace")
        except OSError:
            return False
        return stat_text.rsplit(")", 1)[1].split()[0] != "Z"
    try:
        os.kill(process_id, 0)
    except OSError:
        return False
    return True


def _is_gone_within(process_id: int, seconds: float) -> bool:
    gives_up_at = time.monotonic() + seconds
    while _is_running(process_id):
        if time.monotonic() >= gives_up_at:
            return False
        time.sleep(0.05)
    return True


def _grandchild_process_id(pid_path: Path) -> int:
    gives_up_at = time.monotonic() + GRANDCHILD_PID_WAIT_SECONDS
    while not pid_path.exists() or not pid_path.read_text(encoding="ascii").strip():
        assert time.monotonic() < gives_up_at, "the grandchild never wrote its process id"
        time.sleep(0.05)
    return int(pid_path.read_text(encoding="ascii"))


def test_child_stdout_should_end_a_grandchild_that_holds_the_output_pipe(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX process groups")
    pid_path = tmp_path / "grandchild.pid"
    command = [sys.executable, "-c", CHILD_STARTS_A_SLEEPING_GRANDCHILD, GRANDCHILD_WRITES_ITS_PID_AND_SLEEPS, str(pid_path)]
    answer = child_stdout(command, GRANDCHILD_READ_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK)
    grandchild_process_id = _grandchild_process_id(pid_path)
    try:
        assert answer is None
        assert _is_gone_within(grandchild_process_id, GRANDCHILD_GONE_WITHIN_SECONDS)
    finally:
        if _is_running(grandchild_process_id):
            os.kill(grandchild_process_id, signal.SIGKILL)


def test_child_stdout_should_end_a_grandchild_that_holds_the_output_pipe_on_windows(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("taskkill runs only on Windows")
    pid_path = tmp_path / "grandchild.pid"
    command = [sys.executable, "-c", CHILD_STARTS_A_SLEEPING_GRANDCHILD, GRANDCHILD_WRITES_ITS_PID_AND_SLEEPS, str(pid_path)]
    started_at = time.monotonic()
    answer = child_stdout(command, GRANDCHILD_READ_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK)
    stop_seconds = time.monotonic() - started_at - GRANDCHILD_READ_TIMEOUT_SECONDS
    grandchild_process_id = _grandchild_process_id(pid_path)
    assert answer is None
    assert stop_seconds <= KILL_GRACE_SECONDS + WINDOWS_STOP_SLACK_SECONDS
    tasklist = subprocess.run(
        ["tasklist", "/FI", f"PID eq {grandchild_process_id}", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert str(grandchild_process_id) not in tasklist.stdout


def test_child_stdout_should_stop_a_windows_child_with_a_hidden_bounded_tree_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform == "win32":
        pytest.skip("on Windows the read makes a job object and needs no taskkill")
    all_stop_calls: list[tuple[list[str], dict[str, object]]] = []

    def record_stop(all_command_words: list[str], **all_options: object) -> subprocess.CompletedProcess[str]:
        all_stop_calls.append((all_command_words, all_options))
        return subprocess.CompletedProcess(all_command_words, 0)

    start_on_this_platform = gate_run_reads.subprocess.Popen

    def start_without_windows_flags(*all_arguments: object, **all_options: object) -> subprocess.Popen[str]:
        all_options.pop("creationflags")
        return start_on_this_platform(*all_arguments, **all_options)

    monkeypatch.setattr(gate_run_reads.sys, "platform", "win32")
    monkeypatch.setattr(gate_run_reads, "hidden_window_creation_flags", lambda: HIDDEN_WINDOW_FLAGS)
    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", start_without_windows_flags)
    monkeypatch.setattr(gate_run_reads.subprocess, "run", record_stop)
    started_at = time.monotonic()
    assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 0.5, ReadSlice.PROOF_AND_LOOK) is None
    assert time.monotonic() - started_at < 0.5 + KILL_GRACE_SECONDS + WINDOWS_STOP_SLACK_SECONDS
    ((all_command_words, all_options),) = all_stop_calls
    assert all_command_words[:4] == ["taskkill", "/T", "/F", "/PID"]
    assert all_command_words[4].isdigit()
    assert all_options["creationflags"] == HIDDEN_WINDOW_FLAGS
    assert 0 < float(str(all_options["timeout"])) < KILL_GRACE_SECONDS


class FakeKernel32:
    """Stands in for kernel32 and notes each job call the read makes."""

    def __init__(self, assigns: bool) -> None:
        self.assigns = assigns
        self.all_calls: list[tuple[str, tuple[object, ...]]] = []

    def CreateJobObjectW(self, *all_arguments: object) -> int:
        self.all_calls.append(("create", all_arguments))
        return FAKE_JOB_HANDLE

    def AssignProcessToJobObject(self, *all_arguments: object) -> int:
        self.all_calls.append(("assign", all_arguments))
        return int(self.assigns)

    def TerminateJobObject(self, *all_arguments: object) -> int:
        self.all_calls.append(("terminate", all_arguments))
        return 1

    def CloseHandle(self, *all_arguments: object) -> int:
        self.all_calls.append(("close", all_arguments))
        return 1


def _windows_read_with_fake_kernel(
    monkeypatch: pytest.MonkeyPatch, kernel: FakeKernel32, script: str, own_timeout_seconds: float
) -> tuple[str | None, list[list[str]]]:
    if sys.platform == "win32":
        pytest.skip("the fake kernel32 stands in for Windows on other platforms")
    all_taskkill_words: list[list[str]] = []
    start_on_this_platform = gate_run_reads.subprocess.Popen

    def start_with_a_handle(*all_arguments: object, **all_options: object) -> subprocess.Popen[str]:
        all_options.pop("creationflags")
        child = start_on_this_platform(*all_arguments, **all_options)
        vars(child)[PROCESS_HANDLE_ATTRIBUTE] = FAKE_PROCESS_HANDLE
        return child

    def record_taskkill(all_command_words: list[str], **all_options: object) -> subprocess.CompletedProcess[str]:
        all_taskkill_words.append(all_command_words)
        return subprocess.CompletedProcess(all_command_words, 0)

    monkeypatch.setattr(gate_run_reads.sys, "platform", "win32")
    monkeypatch.setattr(gate_run_reads, "_kernel32", lambda: kernel)
    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", start_with_a_handle)
    monkeypatch.setattr(gate_run_reads.subprocess, "run", record_taskkill)
    answer = child_stdout([sys.executable, "-c", script], own_timeout_seconds, ReadSlice.PROOF_AND_LOOK)
    return answer, all_taskkill_words


def test_child_stdout_should_end_the_windows_job_of_a_stopped_read(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = FakeKernel32(assigns=True)
    answer, all_taskkill_words = _windows_read_with_fake_kernel(monkeypatch, kernel, SLEEP_THEN_PRINT, 0.5)
    assert answer is None
    assert all_taskkill_words == []
    assert [each_name for each_name, _ in kernel.all_calls] == ["create", "assign", "terminate", "close"]
    assert kernel.all_calls[1][1] == (FAKE_JOB_HANDLE, FAKE_PROCESS_HANDLE)
    assert kernel.all_calls[2][1] == (FAKE_JOB_HANDLE, STOPPED_JOB_EXIT_CODE)


def test_child_stdout_should_close_the_windows_job_of_a_read_that_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = FakeKernel32(assigns=True)
    answer, all_taskkill_words = _windows_read_with_fake_kernel(monkeypatch, kernel, "print('answer')", 5)
    assert answer == "answer\n"
    assert all_taskkill_words == []
    assert [each_name for each_name, _ in kernel.all_calls] == ["create", "assign", "close"]


def test_child_stdout_should_fall_back_to_taskkill_when_the_child_cannot_join_a_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = FakeKernel32(assigns=False)
    answer, all_taskkill_words = _windows_read_with_fake_kernel(monkeypatch, kernel, SLEEP_THEN_PRINT, 0.5)
    assert answer is None
    assert [each_words[:4] for each_words in all_taskkill_words] == [["taskkill", "/T", "/F", "/PID"]]
    assert [each_name for each_name, _ in kernel.all_calls] == ["create", "assign", "close"]


def test_child_stdout_should_end_a_grandchild_that_outlives_its_exited_child(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX process groups")
    pid_path = tmp_path / "grandchild.pid"
    command = [sys.executable, "-c", CHILD_STARTS_A_GRANDCHILD_AND_EXITS, GRANDCHILD_WRITES_ITS_PID_AND_SLEEPS, str(pid_path)]
    answer = child_stdout(command, GRANDCHILD_READ_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK)
    grandchild_process_id = _grandchild_process_id(pid_path)
    try:
        assert answer is None
        assert _is_gone_within(grandchild_process_id, GRANDCHILD_GONE_WITHIN_SECONDS)
    finally:
        if _is_running(grandchild_process_id):
            os.kill(grandchild_process_id, signal.SIGKILL)


def _is_running_on_windows(process_id: int) -> bool:
    tasklist = subprocess.run(
        ["tasklist", "/FI", f"PID eq {process_id}", "/NH"], capture_output=True, text=True, check=False
    )
    return str(process_id) in tasklist.stdout


def test_child_stdout_should_end_a_grandchild_that_outlives_its_exited_child_on_windows(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows job objects")
    pid_path = tmp_path / "grandchild.pid"
    command = [sys.executable, "-c", CHILD_STARTS_A_GRANDCHILD_AND_EXITS, GRANDCHILD_WRITES_ITS_PID_AND_SLEEPS, str(pid_path)]
    with gate_run() as run:
        answer = child_stdout(command, GRANDCHILD_READ_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK)
    grandchild_process_id = _grandchild_process_id(pid_path)
    assert answer is None
    assert run.timed_out_read_count == 1
    assert not _is_running_on_windows(grandchild_process_id)


def test_child_stdout_should_return_the_text_of_a_plain_read_on_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows job objects")
    with gate_run() as run:
        answer = child_stdout([sys.executable, "-c", "print('answer')"], 5, ReadSlice.PROOF_AND_LOOK)
    assert answer == "answer\n"
    assert run.timed_out_read_count == 0


def test_child_stdout_should_mark_the_run_when_the_deadline_cuts_a_read_short(
    all_started_children: list[RecordedChild],
) -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS - 0.4
        assert child_stdout([sys.executable, "-c", SLEEP_THEN_PRINT], 5, ReadSlice.PROOF_AND_LOOK) is None
    (child,) = all_started_children
    assert child.all_wait_timeouts == [pytest.approx(0.4), KILL_GRACE_SECONDS]
    assert child.wait() != 0
    assert run.was_read_cut_short
    assert run.timed_out_read_count == 1


def _lines_that_spend_a_second_each(clock: FakeClock, first_line_at: float) -> Iterator[str]:
    for each_index in range(5):
        clock.now = first_line_at + each_index
        yield f"line {each_index}"


def test_lines_within_slice_should_stop_the_scan_at_the_slice_deadline() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        first_line_at = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS - 3
        all_lines = list(lines_within_slice(_lines_that_spend_a_second_each(clock, first_line_at), ReadSlice.PROOF_AND_LOOK))
    assert all_lines == ["line 0", "line 1", "line 2"]
    assert run.cut_scan_count == 1
    assert not run.was_read_cut_short


def test_lines_within_slice_should_give_every_line_while_the_slice_has_time() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        first_line_at = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS
        all_lines = list(lines_within_slice(_lines_that_spend_a_second_each(clock, first_line_at), ReadSlice.FOLLOWUP))
    with gate_run() as unbounded_run:
        all_unbounded_lines = list(lines_within_slice(_lines_that_spend_a_second_each(clock, 0.0), ReadSlice.PROOF_AND_LOOK))
    assert all_lines == [f"line {each_index}" for each_index in range(5)]
    assert all_unbounded_lines == all_lines
    assert run.cut_scan_count == 0
    assert unbounded_run.cut_scan_count == 0


def test_lines_within_slice_should_give_no_line_once_the_deadline_passed() -> None:
    clock = FakeClock()
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS
        assert list(lines_within_slice(iter(["line 0"]), ReadSlice.PROOF_AND_LOOK)) == []
        assert list(lines_within_slice(iter([]), ReadSlice.PROOF_AND_LOOK)) == []
    assert run.cut_scan_count == 1


class ClockedTranscript(io.BytesIO):
    """A binary transcript whose every read spends one second on a fake clock."""

    def __init__(self, content: bytes, clock: FakeClock) -> None:
        super().__init__(content)
        self.clock = clock
        self.read_count = 0

    def read(self, size: int | None = -1, /) -> bytes:
        self.read_count += 1
        self.clock.now += 1
        return super().read(size)


def test_transcript_lines_within_slice_should_stop_inside_a_line_longer_than_the_time_left() -> None:
    clock = FakeClock()
    transcript = ClockedTranscript(b"old line\n" + b"x" * HUGE_LINE_BYTES, clock)
    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS - SECONDS_LEFT_BEFORE_HUGE_LINE
        all_lines = list(transcript_lines_within_slice(transcript, "utf-8", "replace", ReadSlice.PROOF_AND_LOOK, 10))
    assert all_lines == []
    assert run.cut_scan_count == 1
    assert transcript.read_count == SECONDS_LEFT_BEFORE_HUGE_LINE


def test_transcript_lines_within_slice_should_end_the_scan_at_a_line_over_the_cap_and_count_it_cut() -> None:
    clock = FakeClock()
    transcript = io.BytesIO(b"old line\n" + b"x" * HUGE_LINE_BYTES + b"\nnew line\n")
    with read_deadlines_started(clock), gate_run() as run:
        all_lines = list(
            transcript_lines_within_slice(
                transcript, "utf-8", "replace", ReadSlice.FOLLOWUP, 10, line_byte_cap=HUGE_LINE_BYTES - 1
            )
        )
    assert all_lines == ["new line"]
    assert run.cut_scan_count == 1


def test_transcript_lines_within_slice_should_give_every_line_newest_first_while_the_slice_has_time() -> None:
    clock = FakeClock()
    transcript = ClockedTranscript(b"one\r\ntwo\rthree\n", clock)
    with read_deadlines_started(clock), gate_run() as run:
        all_lines = list(transcript_lines_within_slice(transcript, "utf-8", "replace", ReadSlice.FOLLOWUP, 4))
    assert all_lines == ["three", "two", "one"]
    assert run.cut_scan_count == 0


def test_answer_within_allowance_should_bound_the_whole_read() -> None:
    clock = FakeClock()
    release = threading.Event()

    def held_read(allowance: float) -> list[str]:
        release.wait(HELD_READ_GIVES_UP_SECONDS)
        return ["late"]

    with read_deadlines_started(clock), gate_run() as run:
        clock.now = CLOCK_START + PROOF_AND_LOOK_READS_SECONDS + FOLLOWUP_READS_SECONDS - 0.3
        try:
            answer = answer_within_allowance(held_read, 4, ReadSlice.FOLLOWUP)
        finally:
            release.set()
    assert answer is None
    assert run.was_read_cut_short
    assert run.timed_out_read_count == 1


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


def _registered_gate_timeout_seconds() -> int:
    all_registration_fields = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))
    all_timeouts = [
        each_hook["timeout"]
        for each_group in all_registration_fields["hooks"]["PreToolUse"]
        for each_hook in each_group["hooks"]
        if each_hook.get("command", "").endswith(GATE_COMMAND_SUFFIX)
    ]
    assert len(all_timeouts) == 1
    return all_timeouts[0]


def test_both_followup_reads_should_fit_inside_their_reserved_slice() -> None:
    assert READ_TIMEOUT_SECONDS * 2 <= FOLLOWUP_READS_SECONDS


def test_registered_timeout_should_outlast_every_read_deadline_and_kill_grace() -> None:
    last_read_ends_at = (
        PROOF_AND_LOOK_READS_SECONDS
        + FOLLOWUP_READS_SECONDS
        + KILL_GRACE_SECONDS * MOST_CUT_READS_PER_RUN
    )
    assert _registered_gate_timeout_seconds() >= last_read_ends_at + STARTUP_AND_OUTPUT_MARGIN_SECONDS


def test_gate_run_reads_should_parse_under_the_oldest_supported_python() -> None:
    source = Path(gate_run_reads.__file__).read_text(encoding="utf-8")
    assert ast.parse(source, feature_version=OLDEST_SUPPORTED_PYTHON).body
