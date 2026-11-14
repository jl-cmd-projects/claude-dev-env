"""Behavior tests for the answers one pull request lifecycle gate run remembers."""

import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking.gate_run_reads import answer_once, gate_run


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
