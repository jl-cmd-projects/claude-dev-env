#!/usr/bin/env python3
"""PreToolUse context note: several pieces in one commit or pull request get one level each.

This hook never blocks, denies, or exits non-zero. It reads the author's own
words when an agent runs ``git commit`` (the subject from ``-m``, ``--message``,
or the file ``-F`` names) or opens a pull request (``gh pr create``,
``pull_request.py create``, a ``create_pull_request`` tool). When those words
name several pieces, it adds one short note as ``additionalContext``::

    Your own words name several pieces in this commit: "always publish drawn
    icons"; "put Tips on the tray". Each piece gets its own commit and its own
    stack level ... The commit that is running holds every piece. To split it,
    run `git reset --soft HEAD~1` ...

The analysis lives in ``pieces_per_level_analysis.py``. This script is the
parent that runs it:

1. A cheap linear check on the raw payload. The call must hold a ``git commit``
   with a message flag, or a pull request create, as whole words, and its text
   must hold a clause separator (a comma, a semicolon, "and") or a body option.
   The MCP create tool needs a separator in its title or a body. Any other call
   gets no note, and no child process starts.
2. The analysis runs in a child process (this script with ``--analyze``) under
   one wall-clock deadline for the whole child, from start to exit:
   ``TOTAL_DEADLINE_SECONDS``, with at most ``EXIT_WAIT_SECONDS`` of it spent
   waiting for the exit after the output ends. A child that is not done by then
   is killed, and the hook prints nothing and exits 0. A child process bounds it,
   not a thread: a regular expression holds the interpreter lock, so a thread
   could not give control back to a timer. The parent imports none of the
   analysis modules, so a call that is no candidate pays only for this file.
3. Any error in the parent gives no output and exit 0.

The environment variable ``PIECES_NOTE_TEST_DEADLINE_SECONDS`` sets the
deadline. It is for tests only, so that a loaded machine does not cost a test
its note. Hook settings never set it.

The command or tool call runs with its normal permission flow.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import IO

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

from hooks_constants.followup_pr_dedupe_constants import CREATE_PULL_REQUEST_TOOL_SUFFIX
from hooks_constants.pieces_per_level_note_constants import (
    ANALYSIS_MODULE_NAME,
    ANALYZE_FLAG,
    BODY_INPUT_KEY,
    BODY_OPTION_PATTERN,
    CLAUSE_SEPARATOR_PRECHECK_PATTERN,
    COMMAND_INPUT_KEY,
    COMMIT_MESSAGE_FLAG_PATTERN,
    COMMIT_WORD_PATTERN,
    CREATE_NO_WINDOW_ATTRIBUTE,
    DEADLINE_ENVIRONMENT_VARIABLE,
    EXIT_WAIT_SECONDS,
    GH_PROGRAM_NAME,
    GIT_WORD_PATTERN,
    MAXIMUM_COMMAND_CHARACTERS,
    PULL_REQUEST_CREATE_PATTERN,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    TITLE_INPUT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOTAL_DEADLINE_SECONDS,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES


def deadline_seconds(all_environment: Mapping[str, str]) -> float:
    """Return the total child deadline, or the default for a missing or bad test override.

    Args:
        all_environment: The process environment.
    """
    try:
        override_seconds = float(all_environment.get(DEADLINE_ENVIRONMENT_VARIABLE, ""))
    except ValueError:
        return TOTAL_DEADLINE_SECONDS
    is_usable = isfinite(override_seconds) and override_seconds > 0
    return override_seconds if is_usable else TOTAL_DEADLINE_SECONDS


def _is_commit_with_message(command: str) -> bool:
    git_match = GIT_WORD_PATTERN.search(command)
    if git_match is None:
        return False
    commit_match = COMMIT_WORD_PATTERN.search(command, git_match.end())
    if commit_match is None:
        return False
    return COMMIT_MESSAGE_FLAG_PATTERN.search(command, commit_match.end()) is not None


def _is_pull_request_create(command: str) -> bool:
    is_gh_create = (
        GH_PROGRAM_NAME in command and PULL_REQUEST_CREATE_PATTERN.search(command) is not None
    )
    return is_gh_create or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(command) is not None


def _could_name_several_pieces_in_command(command: object) -> bool:
    if not isinstance(command, str) or len(command) > MAXIMUM_COMMAND_CHARACTERS:
        return False
    if not (_is_commit_with_message(command) or _is_pull_request_create(command)):
        return False
    return (
        CLAUSE_SEPARATOR_PRECHECK_PATTERN.search(command) is not None
        or BODY_OPTION_PATTERN.search(command) is not None
    )


def could_hold_a_note(all_hook_fields: dict[str, object]) -> bool:
    """Return whether a PreToolUse call could name several pieces, by a cheap linear check.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    all_tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    tool_name = all_hook_fields.get(TOOL_NAME_KEY)
    if not isinstance(all_tool_input, dict) or not isinstance(tool_name, str):
        return False
    if tool_name in SHELL_TOOL_NAMES:
        return _could_name_several_pieces_in_command(all_tool_input.get(COMMAND_INPUT_KEY))
    if not tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        return False
    title = all_tool_input.get(TITLE_INPUT_KEY)
    body = all_tool_input.get(BODY_INPUT_KEY)
    has_separator = isinstance(title, str) and CLAUSE_SEPARATOR_PRECHECK_PATTERN.search(title)
    return bool(has_separator or (isinstance(body, str) and body))


def _pump_child_output(
    stream: IO[bytes], finished_signal: threading.Event, all_chunks: list[bytes]
) -> None:
    try:
        all_chunks.append(stream.read())
    except (OSError, ValueError):
        pass
    finally:
        finished_signal.set()


def _send_payload(stream: IO[bytes], payload: bytes) -> None:
    try:
        stream.write(payload)
        stream.close()
    except (OSError, ValueError):
        pass


def _start_child(all_arguments: list[str]) -> subprocess.Popen[bytes] | None:
    try:
        return subprocess.Popen(
            all_arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, CREATE_NO_WINDOW_ATTRIBUTE, 0),
        )
    except OSError:
        return None


def _start_io_threads(
    child: subprocess.Popen[bytes], payload: bytes
) -> tuple[threading.Event, list[bytes]]:
    finished_signal = threading.Event()
    all_chunks: list[bytes] = []
    threading.Thread(
        target=_pump_child_output, args=(child.stdout, finished_signal, all_chunks), daemon=True
    ).start()
    threading.Thread(target=_send_payload, args=(child.stdin, payload), daemon=True).start()
    return finished_signal, all_chunks


def _kill(child: subprocess.Popen[bytes]) -> None:
    try:
        child.kill()
    except OSError:
        pass


def _remaining_seconds(deadline_at: float) -> float:
    return max(0.0, deadline_at - time.monotonic())


def analysis_output(payload: bytes, all_arguments: list[str], total_seconds: float) -> bytes:
    """Run the analysis as a child process and return what it printed, or nothing.

    Starting, writing the payload, reading the output, and waiting for the exit
    all happen inside ``total_seconds``. The payload goes in from a thread, so a
    child that never reads cannot hold the caller. A child not done by then is killed.

    Args:
        payload: The raw PreToolUse payload the child reads on standard input.
        all_arguments: The child command line.
        total_seconds: The wall-clock time for the whole child, start to exit.

    Returns:
        The child's standard output when it exits 0 in time, else empty bytes.
    """
    deadline_at = time.monotonic() + total_seconds
    child = _start_child(all_arguments)
    if child is None or child.stdin is None or child.stdout is None:
        return b""
    finished_signal, all_chunks = _start_io_threads(child, payload)
    try:
        is_finished = finished_signal.wait(_remaining_seconds(deadline_at))
        exit_wait = min(EXIT_WAIT_SECONDS, _remaining_seconds(deadline_at))
        return all_chunks[0] if is_finished and child.wait(exit_wait) == 0 else b""
    except subprocess.TimeoutExpired:
        return b""
    finally:
        _kill(child)


def _child_arguments() -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), ANALYZE_FLAG]


def _run_within_deadline() -> int:
    payload = sys.stdin.buffer.read()
    all_hook_fields = json.loads(payload)
    if not isinstance(all_hook_fields, dict) or not could_hold_a_note(all_hook_fields):
        return 0
    output = analysis_output(payload, _child_arguments(), deadline_seconds(os.environ))
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


def main() -> int:
    """Print the note when the words name several pieces, inside the wall-clock deadline.

    Returns:
        0 in every case; the note travels in the JSON output.
    """
    if ANALYZE_FLAG in sys.argv[1:]:
        return importlib.import_module(ANALYSIS_MODULE_NAME).main()
    try:
        return _run_within_deadline()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
