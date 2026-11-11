"""Bound tests for the pieces-per-level note.

The hook finishes inside a wall-clock budget whatever the input holds. These
tests feed it inputs that were slow before the bounds existed and read the
silence, the exit status, and the wall time.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

import commit_and_pull_request_words
import piece_clauses
import pieces_per_level_note
from hooks_constants.pieces_per_level_note_constants import (
    ANALYSIS_BUDGET_SECONDS,
    COMMIT_NEXT_COMMAND,
    MAXIMUM_BODY_CHARACTERS,
    MAXIMUM_TITLE_CHARACTERS,
)

SCRIPT_PATH = Path(__file__).resolve().parent / "pieces_per_level_note.py"
ENTRY_SECONDS_BOUND = 1.0
OVER_BARE_START_SECONDS_BOUND = 1.0
INTERPRETER_STARTS_PER_RUN = 2
RUNS_PER_INPUT = 3
MIXED_SUBJECT = (
    "fix(convert): always publish drawn icons, put Tips on the tray, stop the label smear"
)
MANY_SUBSTITUTIONS = "$(" * 3_900 + " git commit -m x"
SLOW_CHILD_SECONDS = 30
PROOF_HEADING = "## Proof in practice"


def _bare_start_seconds() -> float:
    all_runs = []
    for _ in range(3):
        started_at = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], check=False)
        all_runs.append(time.perf_counter() - started_at)
    return min(all_runs)


def _run_hook(payload: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], float]:
    started_at = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed, time.perf_counter() - started_at


def _shell_payload(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _mcp_payload(title: str, body: str) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": title, "body": body},
    }


def _seconds_of(call, *all_arguments: object) -> tuple[object, float]:
    started_at = time.perf_counter()
    result = call(*all_arguments)
    return result, time.perf_counter() - started_at


READY_PRINT = "import sys; sys.stdout.write('ready' + chr(10)); sys.stdout.flush(); "
STARTUP_ALLOWANCE_FOR_TESTS = 20.0


def _child_arguments(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_a_slow_analysis_is_cut_off_at_the_budget_with_silence() -> None:
    all_slow_arguments = _child_arguments(READY_PRINT + f"import time; time.sleep({SLOW_CHILD_SECONDS})")
    started_at = time.perf_counter()
    output = pieces_per_level_note.analysis_output(
        b"{}", all_slow_arguments, 0.3, STARTUP_ALLOWANCE_FOR_TESTS
    )
    assert output == b""
    assert time.perf_counter() - started_at < SLOW_CHILD_SECONDS / 3


def test_the_budget_starts_when_the_child_reports_ready_not_when_it_starts() -> None:
    all_slow_start_arguments = _child_arguments(
        "import time; time.sleep(1.0); " + READY_PRINT + "sys.stdin.read(); sys.stdout.write('done')"
    )
    output = pieces_per_level_note.analysis_output(
        b"{}", all_slow_start_arguments, 0.5, STARTUP_ALLOWANCE_FOR_TESTS
    )
    assert output == b"done"


def test_a_child_that_never_reports_ready_is_cut_off_at_the_startup_allowance() -> None:
    all_silent_arguments = _child_arguments(f"import time; time.sleep({SLOW_CHILD_SECONDS})")
    started_at = time.perf_counter()
    output = pieces_per_level_note.analysis_output(b"{}", all_silent_arguments, 30, 0.5)
    assert output == b""
    assert time.perf_counter() - started_at < SLOW_CHILD_SECONDS / 3


def test_an_analysis_that_finishes_in_time_passes_its_output_through() -> None:
    all_fast_arguments = _child_arguments(READY_PRINT + "sys.stdin.read(); sys.stdout.write('done')")
    output = pieces_per_level_note.analysis_output(
        b"{}", all_fast_arguments, 30, STARTUP_ALLOWANCE_FOR_TESTS
    )
    assert output == b"done"


def test_an_analysis_that_exits_non_zero_gives_no_output() -> None:
    all_failing_arguments = _child_arguments(
        READY_PRINT + "sys.stdin.read(); sys.stdout.write('x'); sys.exit(3)"
    )
    output = pieces_per_level_note.analysis_output(
        b"{}", all_failing_arguments, 30, STARTUP_ALLOWANCE_FOR_TESTS
    )
    assert output == b""


def test_the_budget_is_about_half_a_second() -> None:
    assert 0.3 <= ANALYSIS_BUDGET_SECONDS <= 0.8


@pytest.mark.parametrize(
    "payload",
    [
        _shell_payload(MANY_SUBSTITUTIONS),
        _mcp_payload("fix: a" + " " * 100_000 + "b", ""),
        _mcp_payload("fix: a" + "(" * 200_000, ""),
        _mcp_payload("fix: a", PROOF_HEADING + " " * 60_000 + "x"),
    ],
    ids=["substitutions", "title spaces", "title parentheses", "body heading spaces"],
)
def test_an_input_that_was_slow_gives_silence_exit_zero_and_a_short_wall_time(
    payload: dict[str, object],
) -> None:
    bare_start_seconds = _bare_start_seconds()
    all_runs = [_run_hook(payload) for _ in range(RUNS_PER_INPUT)]
    for each_completed, _each_seconds in all_runs:
        assert each_completed.returncode == 0
        assert each_completed.stdout == ""
        assert each_completed.stderr == ""
    fastest_seconds = min(each_seconds for _each_completed, each_seconds in all_runs)
    assert fastest_seconds - INTERPRETER_STARTS_PER_RUN * bare_start_seconds < OVER_BARE_START_SECONDS_BOUND


def test_a_commit_with_many_substitutions_gets_no_note_within_the_entry_bound() -> None:
    all_fields = {"tool_name": "Bash", "tool_input": {"command": MANY_SUBSTITUTIONS}, "cwd": ""}
    output, elapsed_seconds = _seconds_of(pieces_per_level_note.decide_hook_output, all_fields)
    assert output is None
    assert elapsed_seconds < ENTRY_SECONDS_BOUND


def test_a_heredoc_message_still_gets_the_note_with_one_substitution() -> None:
    command = f"git commit -m \"$(cat <<'EOF'{chr(10)}{MIXED_SUBJECT}{chr(10)}EOF{chr(10)})\""
    all_fields = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ""}
    assert "stop the label smear" in json.dumps(
        pieces_per_level_note.decide_hook_output(all_fields)
    )


def test_the_commit_and_pull_request_readers_unwrap_the_command_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_calls: list[str] = []
    real_unwrap = commit_and_pull_request_words.all_wrapped_command_texts

    def counting_unwrap(command: str, *all_arguments: object) -> list[str]:
        all_calls.append(command)
        return real_unwrap(command, *all_arguments)

    monkeypatch.setattr(commit_and_pull_request_words, "all_wrapped_command_texts", counting_unwrap)
    commit_and_pull_request_words.clear_parse_cache()
    command = "git commit -m 'fix(x): one thing' && gh pr create --title t"
    all_fields = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ""}
    assert pieces_per_level_note.decide_hook_output(all_fields) is None
    assert len(all_calls) == 1


def test_a_command_with_many_substitution_markers_is_not_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_calls: list[str] = []
    monkeypatch.setattr(
        commit_and_pull_request_words,
        "all_wrapped_command_texts",
        lambda command, *_all_arguments: all_calls.append(command) or [command],
    )
    commit_and_pull_request_words.clear_parse_cache()
    commit_and_pull_request_words.commit_subjects(MANY_SUBSTITUTIONS, "")
    assert all_calls == []


@pytest.mark.parametrize(
    "title",
    [
        "fix: a" + " " * 20_000 + "b",
        "fix: a" + " " * 100_000 + "b",
        "fix: a" + "(" * 200_000,
        "fix: a" + "`" * 100_000,
        "fix: a" + ", " * 100_000,
    ],
    ids=["20k spaces", "100k spaces", "200k parentheses", "100k backticks", "100k commas"],
)
def test_a_long_title_names_no_pieces_within_the_entry_bound(title: str) -> None:
    all_pieces, elapsed_seconds = _seconds_of(piece_clauses.subject_pieces, title)
    assert all_pieces == []
    assert elapsed_seconds < ENTRY_SECONDS_BOUND


def test_a_title_at_the_cap_still_names_its_pieces() -> None:
    assert len(MIXED_SUBJECT) < MAXIMUM_TITLE_CHARACTERS
    assert len(piece_clauses.subject_pieces(MIXED_SUBJECT)) == 3


@pytest.mark.parametrize(
    "body",
    [
        PROOF_HEADING + " " * 60_000 + "x",
        "## What this does" + " " * 60_000 + "x",
        PROOF_HEADING + chr(10) + "Without it " + ";" * 100_000,
        PROOF_HEADING + chr(10) + "- " + "**a " * 100_000,
        (PROOF_HEADING + chr(10) + "Without the change: x" + chr(10)) * 5_000,
    ],
    ids=["proof heading", "what heading", "semicolons", "bold bullets", "many lines"],
)
def test_a_hostile_body_is_read_within_the_entry_bound(body: str) -> None:
    all_counts, elapsed_seconds = _seconds_of(
        lambda text: (piece_clauses.proof_pair_count(text), piece_clauses.topic_bullets(text)),
        body,
    )
    assert all_counts[0] <= len(body)
    assert elapsed_seconds < ENTRY_SECONDS_BOUND


def test_a_body_is_read_only_up_to_the_character_cap() -> None:
    pair = chr(10).join(["Without the change: a failed.", "With the change: a passed."])
    filler = chr(10) + "x" * (MAXIMUM_BODY_CHARACTERS + 10)
    body = PROOF_HEADING + chr(10) + pair + chr(10) + filler + chr(10) + pair
    assert piece_clauses.proof_pair_count(body) == 1


def test_a_heading_line_padded_past_the_line_cap_still_opens_its_section() -> None:
    pair = chr(10).join(["Without the change: a failed.", "With the change: a passed."])
    body = PROOF_HEADING + " " * 5_000 + chr(10) + pair + chr(10) + pair
    assert piece_clauses.proof_pair_count(body) == 2


def test_the_commit_note_holds_the_commit_and_names_the_split_commands() -> None:
    assert "git add -p" not in COMMIT_NEXT_COMMAND
    assert "The commit that is running holds every piece." in COMMIT_NEXT_COMMAND
    assert "`git reset --soft HEAD~1`" in COMMIT_NEXT_COMMAND
    assert "`git add <paths of the first piece>`" in COMMIT_NEXT_COMMAND

