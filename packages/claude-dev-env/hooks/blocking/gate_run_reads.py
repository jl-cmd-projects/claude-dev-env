"""Remember each read the pull request lifecycle gate makes, for one gate run.

One gate run is one call of ``decision_for``. Several checks in that run
ask git or GitHub the same question, such as the merge base of the head
branch. The first ask reads; each later ask in the same run gets the
remembered answer, unanswered ones included::

    with gate_run():
        answer_once(("origin", "/repo"), read_origin)  -> runs read_origin
        answer_once(("origin", "/repo"), read_origin)  -> the remembered answer
    answer_once(("origin", "/repo"), read_origin)      -> runs read_origin: no run is open

The run closes when its ``with`` block ends, so a later payload in the
same process, such as the next test, starts with nothing remembered.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TypeVar, cast

AnswerType = TypeVar("AnswerType")


@dataclass
class GateRun:
    """The answers one gate run has read, keyed by the question each read asks."""

    answer_by_question: dict[Hashable, object] = field(default_factory=dict)


open_gate_run: ContextVar[GateRun | None] = ContextVar("open_gate_run", default=None)


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
