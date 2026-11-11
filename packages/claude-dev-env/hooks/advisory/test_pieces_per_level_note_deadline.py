"""Deadline tests for the pieces-per-level note.

The hook runs its analysis in a child process under one wall-clock deadline for
the whole child, from start to exit. These tests use fake children that stall
at each stage and read the silence, the exit status, the wall time, and whether
a child was started.
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

import pieces_per_level_note
from hooks_constants.pieces_per_level_note_constants import (
    DEADLINE_ENVIRONMENT_VARIABLE,
    EXIT_WAIT_SECONDS,
    TOTAL_DEADLINE_SECONDS,
)

STALL_SECONDS = 30
SHORT_DEADLINE_SECONDS = 0.5
RETURN_BOUND_SECONDS = STALL_SECONDS / 3
MIXED_SUBJECT = (
    "fix(convert): always publish drawn icons, put Tips on the tray, stop the label smear"
)
ALL_RUNNER_SOURCE = (
    "import sys; sys.path.insert(0, {advisory!r}); import pieces_per_level_note as hook; "
    "hook._child_arguments = lambda: [sys.executable, '-c', {child!r}]; sys.exit(hook.main())"
)


def _child_arguments(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _shell_fields(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _mcp_fields(title: str, body: str) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": title, "body": body},
    }


def _bare_start_seconds() -> float:
    all_runs = []
    for _ in range(3):
        started_at = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], check=False)
        all_runs.append(time.perf_counter() - started_at)
    return min(all_runs)


def _run_hook_with_fake_child(
    fields: dict[str, object], child_code: str
) -> tuple[subprocess.CompletedProcess[str], float]:
    runner_source = ALL_RUNNER_SOURCE.format(advisory=advisory_directory, child=child_code)
    started_at = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-c", runner_source],
        input=json.dumps(fields),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed, time.perf_counter() - started_at


def _marker_child_code(marker_path: Path) -> str:
    return (
        f"open({str(marker_path)!r}, 'w').write('started'); "
        f"import time; time.sleep({STALL_SECONDS})"
    )


def test_the_default_deadline_is_about_one_second_and_the_exit_wait_fits_inside_it() -> None:
    assert 0.5 <= TOTAL_DEADLINE_SECONDS <= 1.5
    assert 0 < EXIT_WAIT_SECONDS <= TOTAL_DEADLINE_SECONDS / 2


def test_a_child_that_never_prints_is_killed_at_the_deadline() -> None:
    started_at = time.perf_counter()
    output = pieces_per_level_note.analysis_output(
        b"{}", _child_arguments(f"import time; time.sleep({STALL_SECONDS})"), SHORT_DEADLINE_SECONDS
    )
    assert output == b""
    assert time.perf_counter() - started_at < RETURN_BOUND_SECONDS


def test_a_child_that_never_reads_a_large_payload_is_killed_at_the_deadline() -> None:
    started_at = time.perf_counter()
    output = pieces_per_level_note.analysis_output(
        b"x" * 20_000_000,
        _child_arguments(f"import time; time.sleep({STALL_SECONDS})"),
        SHORT_DEADLINE_SECONDS,
    )
    assert output == b""
    assert time.perf_counter() - started_at < RETURN_BOUND_SECONDS


def test_a_child_that_prints_then_hangs_after_closing_its_output_is_cut_off_at_the_exit_wait() -> (
    None
):
    all_arguments = _child_arguments(
        "import os, sys, time; sys.stdin.read(); sys.stdout.write('late'); sys.stdout.flush(); "
        f"os.close(1); time.sleep({STALL_SECONDS})"
    )
    started_at = time.perf_counter()
    output = pieces_per_level_note.analysis_output(b"{}", all_arguments, 3)
    assert output == b""
    assert time.perf_counter() - started_at < RETURN_BOUND_SECONDS


def test_a_child_that_starts_slowly_still_inside_the_deadline_passes_its_output_through() -> None:
    all_arguments = _child_arguments(
        "import sys, time; time.sleep(0.3); sys.stdin.read(); sys.stdout.write('done')"
    )
    assert pieces_per_level_note.analysis_output(b"{}", all_arguments, 20) == b"done"


def test_a_child_past_the_deadline_is_killed_and_does_not_finish_its_work(tmp_path: Path) -> None:
    marker_path = tmp_path / "finished.txt"
    all_arguments = _child_arguments(
        f"import time; time.sleep(2.0); open({str(marker_path)!r}, 'w').write('finished')"
    )
    assert (
        pieces_per_level_note.analysis_output(b"{}", all_arguments, SHORT_DEADLINE_SECONDS) == b""
    )
    time.sleep(3.0)
    assert not marker_path.exists()


def test_an_analysis_that_exits_non_zero_gives_no_output() -> None:
    all_arguments = _child_arguments(
        "import sys; sys.stdin.read(); sys.stdout.write('x'); sys.exit(3)"
    )
    assert pieces_per_level_note.analysis_output(b"{}", all_arguments, 20) == b""


def test_a_child_that_cannot_start_gives_no_output() -> None:
    assert (
        pieces_per_level_note.analysis_output(b"{}", ["definitely-not-a-program-name"], 20) == b""
    )


def test_the_hook_prints_nothing_and_exits_zero_when_its_child_never_prints(tmp_path: Path) -> None:
    marker_path = tmp_path / "started.txt"
    bare_start_seconds = _bare_start_seconds()
    all_runs = [
        _run_hook_with_fake_child(
            _shell_fields(f'git commit -m "{MIXED_SUBJECT}"'), _marker_child_code(marker_path)
        )
        for _ in range(3)
    ]
    for each_completed, _each_seconds in all_runs:
        assert each_completed.returncode == 0
        assert each_completed.stdout == ""
        assert each_completed.stderr == ""
    assert marker_path.exists()
    fastest_seconds = min(each_seconds for _each_completed, each_seconds in all_runs)
    assert fastest_seconds < 3 * bare_start_seconds + TOTAL_DEADLINE_SECONDS + 1.0


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git status",
        "git log --grep=commit",
        "mkdir createdir",
        "npm run create-app",
        'git commit -m "fix(icons): put Tips on the tray"',
        "git commit",
    ],
)
def test_a_call_that_cannot_name_several_pieces_starts_no_child(
    command: str, tmp_path: Path
) -> None:
    marker_path = tmp_path / "started.txt"
    completed, _elapsed_seconds = _run_hook_with_fake_child(
        _shell_fields(command), _marker_child_code(marker_path)
    )
    assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", "")
    assert not marker_path.exists()


@pytest.mark.parametrize(
    "fields",
    [
        _shell_fields(f'git commit -m "{MIXED_SUBJECT}"'),
        _shell_fields("git commit -F message.txt"),
        _shell_fields("git commit -am 'fix: add a and b'"),
        _shell_fields('git add x && git commit --message="fix: a; b"'),
        _shell_fields('gh pr create --title "fix: a, b" --body-file body.md'),
        _shell_fields("gh pr create --title t --body-file body.md"),
        _shell_fields('python pull_request.py create --title "fix: a, b"'),
        _mcp_fields(MIXED_SUBJECT, ""),
        _mcp_fields("fix: one thing", "## What this does"),
    ],
)
def test_a_call_that_may_name_several_pieces_is_worth_analysing(fields: dict[str, object]) -> None:
    assert pieces_per_level_note.could_hold_a_note(fields)


@pytest.mark.parametrize(
    "fields",
    [
        _shell_fields("ls -la"),
        _shell_fields("git log --grep=commit"),
        _shell_fields("npm run create-app"),
        _shell_fields('git commit -m "fix(icons): put Tips on the tray"'),
        _shell_fields("git status, git diff"),
        _shell_fields("a, b " + "x" * 20_000 + " git commit -m y"),
        _mcp_fields("fix: one thing", ""),
        {"tool_name": "Bash", "tool_input": "git commit -m 'a, b'"},
        {"tool_name": "Bash"},
        {"tool_input": {}},
    ],
)
def test_a_call_that_cannot_name_several_pieces_is_not_worth_analysing(
    fields: dict[str, object],
) -> None:
    assert not pieces_per_level_note.could_hold_a_note(fields)


def test_the_parent_imports_none_of_the_analysis_modules() -> None:
    source = (
        f"import sys; sys.path.insert(0, {advisory_directory!r}); import pieces_per_level_note; "
        "all_names = ('commit_and_pull_request_words', 'piece_clauses', 'pieces_per_level_analysis', "
        "'hooks_constants.pre_tool_use_context_runner'); "
        "print([each for each in all_names if each in sys.modules])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=False
    )
    assert completed.stdout.strip() == "[]"


@pytest.mark.parametrize(
    "raw_payload",
    ["[" * 200_000, "{" * 200_000, '{"a":' * 100_000],
    ids=["brackets", "braces", "nested keys"],
)
def test_a_payload_that_breaks_the_json_parser_gives_silence_and_exit_zero(
    raw_payload: str,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(advisory_directory) / "pieces_per_level_note.py")],
        input=raw_payload,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", "")


def test_the_test_only_environment_variable_sets_the_deadline() -> None:
    assert pieces_per_level_note.deadline_seconds({}) == TOTAL_DEADLINE_SECONDS
    assert pieces_per_level_note.deadline_seconds({DEADLINE_ENVIRONMENT_VARIABLE: "30"}) == 30.0


@pytest.mark.parametrize("raw_value", ["", "soon", "0", "-2", "nan", "inf"])
def test_a_bad_environment_value_keeps_the_default_deadline(raw_value: str) -> None:
    all_environment = {DEADLINE_ENVIRONMENT_VARIABLE: raw_value}
    assert pieces_per_level_note.deadline_seconds(all_environment) == TOTAL_DEADLINE_SECONDS
