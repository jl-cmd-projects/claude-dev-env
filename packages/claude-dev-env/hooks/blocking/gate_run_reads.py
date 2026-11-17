"""Remember and time each read the pull request lifecycle gate makes, for one gate run.

One gate run is one call of ``decision_for``. Several checks in that run
ask git or GitHub the same question, such as the merge base of the head
branch. The first ask reads; each later ask in the same run gets the
remembered answer, unanswered ones included::

    with gate_run():
        answer_once(("origin", "/repo"), read_origin)  -> runs read_origin
        answer_once(("origin", "/repo"), read_origin)  -> the remembered answer
    answer_once(("origin", "/repo"), read_origin)      -> runs read_origin: no run is open

The gate process starts its read deadlines first, so every read fits the
host's timeout. Two deadlines are fixed points from that start::

    start            start + 12 s                 start + 20 s
      |-- proof and look reads --|-- follow-up reads only --|
      |-------------- follow-up reads ----------------------|

A read gets the smaller of its own timeout and the time left in its
slice. A read with no time left is skipped and comes back unanswered. A
child that outlives its allowance is killed with every process it started,
its pipes get a short grace, and it comes back unanswered. The run notes each read the deadline cut
short: a skipped read, and a stopped read whose allowance was below its
own timeout. With no deadlines started, as in a library call or a
unit test, each read keeps its own timeout. The run also counts every read
that stopped at a timeout, its own or the shared deadline, which tells a
read that gave no answer in time apart from one that failed fast.

A transcript scan answers to the same deadlines through
``transcript_lines_within_slice``, which reads the clock before each line
and before each file block, so one long line cannot hold the gate. The run
counts each scan the deadline stopped, apart from the reads it cut short.
"""

from __future__ import annotations

import functools
import math
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, TypeVar, cast

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.gate_child_process import close_job, job_holding, started_child, stop_child
from hooks_constants.gate_run_reads_constants import (
    FOLLOWUP_READS_SECONDS,
    PROOF_AND_LOOK_READS_SECONDS,
)
from hooks_constants.transcript_skill_scan_constants import TRANSCRIPT_BLOCK_BYTES, TRANSCRIPT_LINE_BYTE_CAP
from transcript_skill_scan import ScanCaps, transcript_lines_newest_first

AnswerType = TypeVar("AnswerType")


class ReadSlice(Enum):
    """Which deadline a read answers to, as seconds from the start of the gate process.

    The lifecycle gate reads in ``PROOF_AND_LOOK`` and then ``FOLLOWUP``.
    """

    PROOF_AND_LOOK = PROOF_AND_LOOK_READS_SECONDS
    FOLLOWUP = PROOF_AND_LOOK_READS_SECONDS + FOLLOWUP_READS_SECONDS


@dataclass
class GateRun:
    """What one gate run read and where its clock stopped it.

    ::

        answer_by_question     every answer read in the run, unanswered ones included
        was_read_cut_short     a deadline skipped a read or stopped one below its own timeout
        timed_out_read_count   reads that stopped at a timeout, their own or the shared deadline
        cut_scan_count         transcript scans the deadline stopped
    """

    answer_by_question: dict[Hashable, object] = field(default_factory=dict)
    was_read_cut_short: bool = False
    timed_out_read_count: int = 0
    cut_scan_count: int = 0


@dataclass(frozen=True)
class ReadDeadlines:
    """The clock and the moment the gate process started its read deadlines."""

    clock: Callable[[], float]
    started_at: float

    def seconds_left(self, read_slice: ReadSlice) -> float:
        """Return the seconds left before this slice's deadline, negative once it passed.

        Args:
            read_slice: The slice whose deadline counts.
        """
        return self.started_at + read_slice.value - self.clock()


open_gate_run: ContextVar[GateRun | None] = ContextVar("open_gate_run", default=None)
started_read_deadlines: ContextVar[ReadDeadlines | None] = ContextVar("started_read_deadlines", default=None)


@contextmanager
def gate_run() -> Iterator[GateRun]:
    """Open one gate run for the ``with`` block and close it when the block ends.

    Yields:
        The run, which holds every answer read inside the block.
    """
    run = GateRun()
    token = open_gate_run.set(run)
    try:
        yield run
    finally:
        open_gate_run.reset(token)


@contextmanager
def read_deadlines_started(clock: Callable[[], float] = time.monotonic) -> Iterator[ReadDeadlines]:
    """Start the read deadlines now for the ``with`` block, and drop them when it ends.

    Args:
        clock: The seconds clock the deadlines read; tests pass a fake one.

    Yields:
        The started deadlines.
    """
    deadlines = ReadDeadlines(clock, clock())
    token = started_read_deadlines.set(deadlines)
    try:
        yield deadlines
    finally:
        started_read_deadlines.reset(token)


def answer_once(question: Hashable, read: Callable[[], AnswerType]) -> AnswerType:
    """Return the open run's answer to ``question``, reading it the first time it is asked.

    Args:
        question: What the read asks, such as ``("origin", working_directory)``.
        read: The read that answers it; its None answer is remembered too.

    Returns:
        The answer. With no run open, ``read`` runs on every call.
    """
    run = open_gate_run.get()
    if run is None:
        return read()
    if question not in run.answer_by_question:
        run.answer_by_question[question] = read()
    return cast(AnswerType, run.answer_by_question[question])


def read_allowance(own_timeout_seconds: float, read_slice: ReadSlice) -> float | None:
    """Return how long a read may wait, or None when its slice has no time left.

    ::

        no deadlines started, own timeout 5          -> 5
        3 s left in the proof and look slice, own 5  -> 3
        the slice's deadline passed                  -> None

    Args:
        own_timeout_seconds: The timeout the read carries on its own.
        read_slice: The slice whose deadline the read answers to.
    """
    deadlines = started_read_deadlines.get()
    if deadlines is None:
        return own_timeout_seconds
    seconds_left = deadlines.seconds_left(read_slice)
    if seconds_left <= 0:
        return None
    return min(own_timeout_seconds, seconds_left)


def _note_read_cut_short() -> None:
    run = open_gate_run.get()
    if run is not None:
        run.was_read_cut_short = True


def _note_read_timed_out() -> None:
    run = open_gate_run.get()
    if run is not None:
        run.timed_out_read_count += 1


def _note_scan_cut_short() -> None:
    run = open_gate_run.get()
    if run is not None:
        run.cut_scan_count += 1


def lines_within_slice(all_lines: Iterable[str], read_slice: ReadSlice) -> Iterator[str]:
    """Yield each line until the slice's deadline passes, then stop and count the scan as cut.

    ::

        no deadlines started                  -> every line
        the deadline passes after line 3      -> lines 1 to 3; the open run counts one cut scan
        the deadline passed before the scan   -> no line; the open run counts one cut scan

    A scan that reads through this answers to the same clock as the reads, so
    a long transcript cannot hold the gate past its slice.

    Args:
        all_lines: The lines the scan reads, in the order it reads them.
        read_slice: The slice whose deadline the scan answers to.
    """
    for each_line in all_lines:
        if not _scan_may_continue(read_slice):
            return
        yield each_line


def _scan_may_continue(read_slice: ReadSlice) -> bool:
    if read_allowance(math.inf, read_slice) is not None:
        return True
    _note_scan_cut_short()
    return False


def transcript_lines_within_slice(
    transcript: BinaryIO,
    encoding: str,
    errors: str,
    read_slice: ReadSlice,
    block_size: int = TRANSCRIPT_BLOCK_BYTES,
    line_byte_cap: int = TRANSCRIPT_LINE_BYTE_CAP,
) -> Iterator[str]:
    """Yield the transcript's lines newest first until the slice's deadline passes.

    ::

        b"one\\r\\ntwo\\n", time left              -> "two", "one"
        a 2 GB newest line, deadline in 3 s    -> stops between blocks at the deadline; one cut scan
        a line over the cap, time left         -> the newer lines, then stops; one cut scan

    Args:
        transcript: The transcript opened in binary mode.
        encoding: The text encoding of the transcript.
        errors: The decode errors policy, such as ``"replace"``.
        read_slice: The slice whose deadline the scan answers to.
        block_size: The bytes read from the file at a time.
        line_byte_cap: The most bytes one line may hold.
    """
    keeps_reading = functools.partial(_scan_may_continue, read_slice)
    caps = ScanCaps(line_byte_cap, on_cap_passed=_note_scan_cut_short)
    all_lines = transcript_lines_newest_first(transcript, encoding, errors, block_size, keeps_reading, caps)
    return lines_within_slice(all_lines, read_slice)


def child_stdout(
    all_command_words: Sequence[str],
    own_timeout_seconds: float,
    read_slice: ReadSlice,
    working_directory: str | None = None,
    all_environment_variables: Mapping[str, str] | None = None,
    standard_input: str | None = None,
) -> str | None:
    """Run one read-only child and return its output, or None when it gives no answer.

    ::

        child exits 0 and prints "main\\n"           -> "main\\n"
        child exits 1, or cannot start              -> None
        child outlives its allowance                -> None, after a kill and a short pipe grace
        the slice has no time left                  -> None, and the child never starts

    Args:
        all_command_words: The program and its arguments.
        own_timeout_seconds: The timeout the read carries on its own.
        read_slice: The slice whose deadline the read answers to.
        working_directory: The directory the child runs in, or None for the gate's own.
        all_environment_variables: The child's whole environment, or None for the gate's own.
        standard_input: The text written to the child's input, or None for an empty input.
    """
    allowance = read_allowance(own_timeout_seconds, read_slice)
    if allowance is None:
        _note_read_cut_short()
        return None
    child = started_child(
        all_command_words, working_directory, all_environment_variables, standard_input is not None
    )
    if child is None:
        return None
    job = job_holding(child)
    try:
        return _answer_within(child, allowance, own_timeout_seconds, job, standard_input)
    finally:
        close_job(job)


def _answer_within(
    child: subprocess.Popen[str],
    allowance: float,
    own_timeout_seconds: float,
    job: int | None,
    standard_input: str | None,
) -> str | None:
    try:
        printed_text = child.communicate(input=standard_input, timeout=allowance)[0]
    except subprocess.TimeoutExpired:
        stop_child(child, job)
        _note_read_timed_out()
        if allowance < own_timeout_seconds:
            _note_read_cut_short()
        return None
    return printed_text if child.returncode == 0 else None


def _answers_in_a_daemon_thread(
    read: Callable[[float], AnswerType], allowance: float
) -> tuple[list[AnswerType], list[Exception]]:
    all_answers: list[AnswerType] = []
    all_errors: list[Exception] = []

    def run_read() -> None:
        try:
            all_answers.append(read(allowance))
        except Exception as error:
            all_errors.append(error)

    reader = threading.Thread(target=run_read, daemon=True)
    reader.start()
    reader.join(allowance)
    return all_answers, all_errors


def answer_within_allowance(
    read: Callable[[float], AnswerType], own_timeout_seconds: float, read_slice: ReadSlice
) -> AnswerType | None:
    """Run one read in a daemon thread and return its answer, or None when the allowance runs out first.

    ::

        read answers in 1 s, allowance 4 s   -> its answer
        read raises OSError                  -> the same OSError
        read still waiting after 4 s         -> None; the thread is left to end on its own

    The bound covers the whole read, connect and headers included.

    Args:
        read: The read; it gets the allowance in seconds and must not answer None.
        own_timeout_seconds: The timeout the read carries on its own.
        read_slice: The slice whose deadline the read answers to.
    """
    allowance = read_allowance(own_timeout_seconds, read_slice)
    if allowance is None:
        _note_read_cut_short()
        return None
    all_answers, all_errors = _answers_in_a_daemon_thread(read, allowance)
    if all_errors:
        raise all_errors[0]
    if all_answers:
        return all_answers[0]
    _note_read_timed_out()
    if allowance < own_timeout_seconds:
        _note_read_cut_short()
    return None
