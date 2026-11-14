#!/usr/bin/env python3
"""Stop hook that has a fresh reviewer read each turn's changes after the turn ends.

The agent edits ``src/service.py`` and drops a retry. The turn ends at once.
In the background, a separate ``claude -p`` run reviews only that turn's edits
with ``/code-review low``. A finding exits 2 and wakes the agent with it::

    prompt arrives  ->  snapshot A of the working tree
    agent edits     ->  src/service.py loses @with_retry
    stop            ->  turn ends; snapshot B (parent A), claude -p "/code-review low A..B"
                    ->  exit 2 wakes the agent: "src/service.py:208 - The diff removes ..."
    agent fixes it  ->  stop reviews B..C only, finds nothing, prints nothing

``turn_review_snapshot`` builds the snapshots, and ``turn_review_findings``
reads the findings out of the review text. Edits the user left before the
prompt sit in snapshot A, so the review sees only the agent's work.

Claude Code runs the Stop entry with ``asyncRewake``. A plain ``claude -p``
run has no background, so the same entry holds that stop with exit code 2.
A finding goes to stderr and to the stdout ``reason``. Every other outcome
exits 0 with no output, and its diagnostic goes to ``~/.claude/logs/turn-review.log``.

A stop claims its range before the review starts. Under a lock on the session's
state file, it moves the baseline to snapshot B, marks the turn closed, and
saves both. A second stop during the review starts from B, so no range is
reviewed twice. After the review, the stop waits up to 35 seconds for the
lock, longer than a prompt run may hold it, and changes only the hold count. A stop that never gets that lock
exits 0 with no wake, so each wake is counted.

A prompt marks the turn open. When the last turn is still open, no stop has
claimed it yet: its stop is racing this prompt, or the user interrupted it::

    prompt 1  ->  baseline A, turn open
    stop 1    ->  starts; the next prompt runs before its claim
    prompt 2  ->  turn still open, so A stays the baseline
    stop 1    ->  claims A..B and reviews turn 1's edits

Edits the user made between those two turns are then reviewed too. When a
prompt found the turn open less than 10 seconds before the claim, that prompt
began the next turn, so the stop leaves it open. A later claim closes it,
which ends the open turn an interrupt left behind.

A repository takes part when it is the session's project folder or a folder
directly inside it, and its GitHub origin ``owner/repo`` slug is listed in
``CLAUDE_TURN_REVIEW_REPOSITORIES``. The hook holds a stop at most three times
in a row, skips a turn that changed more than 30 files, and lets the stop
through when the review fails or times out. A stop with no finding below the
cap resets the count, and so does a user's prompt. A prompt within 10 seconds
of the last wake, or one that starts with ``<task-notification``, belongs to
the wake and keeps the count, so a chain of wakes stops at three.
A stop gets 280 seconds of work and a prompt 25, under the 300 and 30
second registrations. A git call or review that would start after that time
is skipped.
The cap and the file limit match Anthropic's security-guidance plugin. The review run
carries ``CLAUDE_TURN_REVIEW_CHILD=1`` and none of the parent session's id,
messaging or ingress variables, and the hook does nothing inside such a run. The review may read
files and run ``git diff``, ``git show`` and ``git log``; every other tool is
denied.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from atomic_file_writer import write_text_atomically
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_time_budget import call_timeout, remaining_seconds, time_budget
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_file_id import session_file_id
from hooks_constants.stop_hook_hold import hold_stop
from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.turn_review_gate_constants import (
    ALL_LOG_PATH_PARTS,
    ALL_PARENT_SESSION_VARIABLES,
    ALL_REVIEW_ALLOWED_TOOLS,
    ALL_REVIEW_DISALLOWED_TOOLS,
    BASELINE_COMMIT_PATTERN,
    BLOCK_REASON_TEMPLATE,
    FINDING_LINE_SEPARATOR,
    GIT_DIRECTORY_NAME,
    HOOK_EVENT_NAME_KEY,
    LOG_LINE_TEMPLATE,
    LOG_TEXT_ENCODING,
    MAXIMUM_BLOCKS_IN_A_ROW,
    MACHINE_PROMPT_PREFIX,
    MAXIMUM_TURN_FILES,
    PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE,
    PROMPT_EVENT_NAME,
    PROMPT_KEY,
    RACING_STOP_WINDOW_SECONDS,
    PROMPT_RUN_BUDGET_SECONDS,
    REPOSITORIES_ENVIRONMENT_VARIABLE,
    REPOSITORY_FINDINGS_SEPARATOR,
    REPOSITORY_FINDINGS_TEMPLATE,
    REPOSITORY_SEPARATOR,
    REVIEW_CHILD_ENVIRONMENT_VARIABLE,
    REVIEW_CHILD_MARKER,
    REVIEW_EFFORT,
    REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    REVIEW_MODEL_ALIAS,
    REVIEW_PROMPT_TEMPLATE,
    REVIEW_RESULT_KEY,
    REVIEW_EXECUTABLE_NAME,
    REVIEW_SETTING_SOURCES_TEXT,
    REVIEW_SETTINGS_TEXT,
    MINIMUM_REVIEW_SECONDS,
    REVIEW_TIMEOUT_SECONDS,
    REVIEW_TOOLS_TEXT,
    RUN_DIAGNOSTIC_TEMPLATE,
    SESSION_ID_KEY,
    STATE_BASELINES_KEY,
    STATE_BLOCKS_KEY,
    STATE_FILE_TEMPLATE,
    STATE_OPEN_TURN_PROMPT_KEY,
    STATE_LAST_WAKE_KEY,
    STATE_TURN_OPEN_KEY,
    STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE,
    STATE_LOCK_BYTE_COUNT,
    STATE_LOCK_FILE_MODE,
    STATE_LOCK_FILE_TEMPLATE,
    STATE_LOCK_OUTCOME_WAIT_SECONDS,
    STATE_LOCK_RETRY_SECONDS,
    STATE_LOCK_WAIT_SECONDS,
    STATE_SAVE_FAILURE_DIAGNOSTIC_TEMPLATE,
    STATE_TEMPORARY_PREFIX,
    STATE_TEXT_ENCODING,
    STOP_EVENT_NAME,
    STOP_HOOK_ACTIVE_KEY,
    STOP_RUN_BUDGET_SECONDS,
    TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE,
    WAKE_PROMPT_WINDOW_SECONDS,
)
from pii_prevention_blocker_parts.repository_exemption import repository_origin_slug
from turn_review_findings import finding_lines
from turn_review_snapshot import turn_changed_paths, working_tree_snapshot

if sys.platform == "win32":

    def _try_file_lock(file_descriptor: int) -> None:
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, STATE_LOCK_BYTE_COUNT)

    def _release_file_lock(file_descriptor: int) -> None:
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, STATE_LOCK_BYTE_COUNT)

else:

    def _try_file_lock(file_descriptor: int) -> None:
        fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_file_lock(file_descriptor: int) -> None:
        fcntl.flock(file_descriptor, fcntl.LOCK_UN)


def _log(diagnostic_text: str) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        log_path = Path.home().joinpath(*ALL_LOG_PATH_PARTS)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding=LOG_TEXT_ENCODING) as log_file:
            log_file.write(LOG_LINE_TEMPLATE.format(timestamp=timestamp, text=diagnostic_text))
    except (OSError, RuntimeError):
        return


def _is_lock_taken(file_descriptor: int) -> bool:
    try:
        _try_file_lock(file_descriptor)
    except OSError:
        return False
    return True


def _acquire_with_wait(file_descriptor: int, wait_seconds: float) -> bool:
    deadline = time.monotonic() + (call_timeout(wait_seconds) or 0)
    while not _is_lock_taken(file_descriptor):
        if time.monotonic() >= deadline:
            return False
        time.sleep(STATE_LOCK_RETRY_SECONDS)
    return True


def _release_and_close(file_descriptor: int, is_locked: bool) -> None:
    try:
        if is_locked:
            _release_file_lock(file_descriptor)
    finally:
        os.close(file_descriptor)


@contextmanager
def _state_lock(session_id: object, wait_seconds: float) -> Iterator[bool]:
    lock_path = Path(tempfile.gettempdir()) / STATE_LOCK_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )
    try:
        file_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, STATE_LOCK_FILE_MODE)
    except OSError:
        yield False
        return
    is_locked = _acquire_with_wait(file_descriptor, wait_seconds)
    try:
        yield is_locked
    finally:
        _release_and_close(file_descriptor, is_locked)


def _opted_in_repository_slugs() -> frozenset[str]:
    listed = os.environ.get(REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    return frozenset(
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    )


def _opted_in_repository_roots(all_slugs: frozenset[str]) -> list[Path]:
    project_directory = os.environ.get(PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE, "")
    if not project_directory or not Path(project_directory).is_dir():
        return []
    project_path = Path(project_directory).resolve()
    all_candidates = [project_path, *sorted(_child_entries(project_path))]
    return [each for each in all_candidates if _is_opted_in_checkout(each, all_slugs)]


def _child_entries(project_path: Path) -> list[Path]:
    try:
        return list(project_path.iterdir())
    except OSError:
        return []


def _is_opted_in_checkout(folder: Path, all_slugs: frozenset[str]) -> bool:
    try:
        is_checkout = folder.is_dir() and (folder / GIT_DIRECTORY_NAME).exists()
    except OSError:
        return False
    return is_checkout and repository_origin_slug(folder) in all_slugs


def _review_command(base_commit: str, turn_commit: str) -> list[str]:
    review_prompt = REVIEW_PROMPT_TEMPLATE.format(
        effort=REVIEW_EFFORT, base_commit=base_commit, turn_commit=turn_commit
    )
    return [
        shutil.which(REVIEW_EXECUTABLE_NAME) or REVIEW_EXECUTABLE_NAME,
        "-p",
        review_prompt,
        "--model",
        REVIEW_MODEL_ALIAS,
        "--output-format",
        "json",
        "--permission-mode",
        "dontAsk",
        "--setting-sources",
        REVIEW_SETTING_SOURCES_TEXT,
        "--tools",
        REVIEW_TOOLS_TEXT,
        "--no-session-persistence",
        "--allowedTools",
        *ALL_REVIEW_ALLOWED_TOOLS,
        "--disallowedTools",
        *ALL_REVIEW_DISALLOWED_TOOLS,
        "--settings",
        REVIEW_SETTINGS_TEXT,
    ]


def _review_environment() -> dict[str, str]:
    all_child_environment_variables = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if each_name not in ALL_PARENT_SESSION_VARIABLES
    }
    all_child_environment_variables[REVIEW_CHILD_ENVIRONMENT_VARIABLE] = REVIEW_CHILD_MARKER
    return all_child_environment_variables


def _write_review_failure(repository_root: Path, failure_text: str) -> None:
    _log(
        REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE.format(
            repository=repository_root.name, reason=failure_text
        )
    )


def _review_stdout(
    repository_root: Path, base_commit: str, turn_commit: str, remaining_seconds: float
) -> str | None:
    try:
        completed_process = subprocess.run(
            _review_command(base_commit, turn_commit),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=remaining_seconds,
            cwd=str(repository_root),
            env=_review_environment(),
            creationflags=hidden_window_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        _write_review_failure(repository_root, "timed out")
        return None
    except OSError as start_error:
        _write_review_failure(repository_root, str(start_error))
        return None
    if completed_process.returncode != 0:
        _write_review_failure(repository_root, f"exit {completed_process.returncode}")
        return None
    return completed_process.stdout


def _review_text(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    remaining_seconds = review_deadline - time.monotonic()
    if remaining_seconds < MINIMUM_REVIEW_SECONDS:
        _write_review_failure(repository_root, "no review time left this stop")
        return None
    review_stdout = _review_stdout(repository_root, base_commit, turn_commit, remaining_seconds)
    if review_stdout is None:
        return None
    try:
        review_result = json.loads(review_stdout)
    except ValueError:
        _write_review_failure(repository_root, "output was not JSON")
        return None
    review_text = review_result.get(REVIEW_RESULT_KEY) if isinstance(review_result, dict) else None
    if not isinstance(review_text, str):
        _write_review_failure(repository_root, "output had no result text")
        return None
    return review_text


def _state_path(session_id: object) -> Path:
    return Path(tempfile.gettempdir()) / STATE_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )


@dataclass
class _ReviewState:
    all_baselines: dict[str, str] = field(default_factory=dict)
    blocks_in_a_row: int = 0
    is_turn_open: bool = False
    last_wake_at: float | None = None
    open_turn_prompt_at: float | None = None


def _saved_time(raw_value: object) -> float | None:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return None
    return float(raw_value)


def _load_state(session_id: object) -> _ReviewState:
    try:
        saved_state = json.loads(_state_path(session_id).read_text(encoding=STATE_TEXT_ENCODING))
    except (OSError, ValueError):
        return _ReviewState()
    if not isinstance(saved_state, dict):
        return _ReviewState()
    raw_baselines = saved_state.get(STATE_BASELINES_KEY)
    all_baselines = {
        each_root: each_commit
        for each_root, each_commit in (
            raw_baselines.items() if isinstance(raw_baselines, dict) else []
        )
        if isinstance(each_root, str)
        and isinstance(each_commit, str)
        and re.fullmatch(BASELINE_COMMIT_PATTERN, each_commit)
    }
    raw_blocks = saved_state.get(STATE_BLOCKS_KEY)
    return _ReviewState(
        all_baselines,
        raw_blocks if isinstance(raw_blocks, int) else 0,
        saved_state.get(STATE_TURN_OPEN_KEY) is True,
        _saved_time(saved_state.get(STATE_LAST_WAKE_KEY)),
        _saved_time(saved_state.get(STATE_OPEN_TURN_PROMPT_KEY)),
    )


def _save_state(session_id: object, review_state: _ReviewState) -> None:
    try:
        write_text_atomically(
            _state_path(session_id),
            json.dumps(
                {
                    STATE_BASELINES_KEY: review_state.all_baselines,
                    STATE_BLOCKS_KEY: review_state.blocks_in_a_row,
                    STATE_TURN_OPEN_KEY: review_state.is_turn_open,
                    STATE_LAST_WAKE_KEY: review_state.last_wake_at,
                    STATE_OPEN_TURN_PROMPT_KEY: review_state.open_turn_prompt_at,
                }
            ),
            STATE_TEXT_ENCODING,
            STATE_TEMPORARY_PREFIX,
            ATOMIC_WRITE_TEMPORARY_SUFFIX,
            False,
        )
    except (OSError, UnicodeError) as save_error:
        _log(STATE_SAVE_FAILURE_DIAGNOSTIC_TEMPLATE.format(detail=save_error))


def _is_wake_prompt(review_state: _ReviewState, prompt_text: object, now: float) -> bool:
    if isinstance(prompt_text, str) and prompt_text.lstrip().startswith(MACHINE_PROMPT_PREFIX):
        return True
    if review_state.last_wake_at is None:
        return False
    return now - review_state.last_wake_at < WAKE_PROMPT_WINDOW_SECONDS


def _prompt_baselines(review_state: _ReviewState, all_roots: list[Path]) -> dict[str, str]:
    all_baselines = dict(review_state.all_baselines) if review_state.is_turn_open else {}
    for each_root in all_roots:
        if str(each_root) in all_baselines:
            continue
        snapshot_commit = working_tree_snapshot(each_root, None)
        if snapshot_commit is not None:
            all_baselines[str(each_root)] = snapshot_commit
    return all_baselines


def _record_prompt_baselines(
    session_id: object, all_roots: list[Path], prompt_text: object
) -> None:
    with _state_lock(session_id, STATE_LOCK_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=PROMPT_EVENT_NAME))
            return
        review_state = _load_state(session_id)
        now = time.time()
        review_state.all_baselines = _prompt_baselines(review_state, all_roots)
        review_state.open_turn_prompt_at = now if review_state.is_turn_open else None
        if not _is_wake_prompt(review_state, prompt_text, now):
            review_state.blocks_in_a_row = 0
        review_state.is_turn_open = True
        _save_state(session_id, review_state)


def _repository_findings(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    all_changed_paths = turn_changed_paths(repository_root, base_commit, turn_commit)
    if len(all_changed_paths) > MAXIMUM_TURN_FILES:
        _log(
            TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE.format(
                repository=repository_root.name,
                count=len(all_changed_paths),
                limit=MAXIMUM_TURN_FILES,
            )
        )
        return None
    if not all_changed_paths:
        return None
    review_text = _review_text(repository_root, base_commit, turn_commit, review_deadline)
    all_finding_lines = finding_lines(review_text or "", all_changed_paths)
    if not all_finding_lines:
        return None
    return REPOSITORY_FINDINGS_TEMPLATE.format(
        repository=repository_root.name,
        findings=FINDING_LINE_SEPARATOR.join(all_finding_lines),
    )


def _claim_locked_turn_ranges(
    session_id: object, all_roots: list[Path]
) -> list[tuple[Path, str, str]]:
    review_state = _load_state(session_id)
    is_capped = review_state.blocks_in_a_row >= MAXIMUM_BLOCKS_IN_A_ROW
    all_next_baselines: dict[str, str] = {}
    all_turn_ranges: list[tuple[Path, str, str]] = []
    for each_root in all_roots:
        base_commit = review_state.all_baselines.get(str(each_root))
        turn_commit = working_tree_snapshot(each_root, base_commit)
        if turn_commit is None:
            continue
        all_next_baselines[str(each_root)] = turn_commit
        if base_commit is not None and base_commit != turn_commit and not is_capped:
            all_turn_ranges.append((each_root, base_commit, turn_commit))
    if not all_turn_ranges and not is_capped:
        review_state.blocks_in_a_row = 0
    review_state.all_baselines = all_next_baselines
    review_state.is_turn_open = (
        review_state.open_turn_prompt_at is not None
        and time.time() - review_state.open_turn_prompt_at < RACING_STOP_WINDOW_SECONDS
    )
    review_state.open_turn_prompt_at = None
    _save_state(session_id, review_state)
    return all_turn_ranges


def _claim_turn_ranges(
    session_id: object, all_roots: list[Path]
) -> list[tuple[Path, str, str]]:
    with _state_lock(session_id, STATE_LOCK_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return []
        return _claim_locked_turn_ranges(session_id, all_roots)


def _save_review_outcome(session_id: object, has_findings: bool) -> None:
    review_state = _load_state(session_id)
    if has_findings:
        review_state.blocks_in_a_row += 1
        review_state.last_wake_at = time.time()
    elif review_state.blocks_in_a_row < MAXIMUM_BLOCKS_IN_A_ROW:
        review_state.blocks_in_a_row = 0
    _save_state(session_id, review_state)


def _is_review_outcome_saved(session_id: object, has_findings: bool) -> bool:
    with _state_lock(session_id, STATE_LOCK_OUTCOME_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return False
        _save_review_outcome(session_id, has_findings)
        return True


def _turn_block_reason(session_id: object, all_roots: list[Path]) -> str | None:
    all_turn_ranges = _claim_turn_ranges(session_id, all_roots)
    if not all_turn_ranges:
        return None
    all_findings: list[str] = []
    review_deadline = time.monotonic() + min(REVIEW_TIMEOUT_SECONDS, remaining_seconds())
    for each_root, each_base_commit, each_turn_commit in all_turn_ranges:
        repository_findings = _repository_findings(
            each_root, each_base_commit, each_turn_commit, review_deadline
        )
        if repository_findings is not None:
            all_findings.append(repository_findings)
    if not _is_review_outcome_saved(session_id, bool(all_findings)) or not all_findings:
        return None
    return BLOCK_REASON_TEMPLATE.format(
        all_findings=REPOSITORY_FINDINGS_SEPARATOR.join(all_findings)
    )


def _handle_event(hook_input: dict, hook_event_name: object) -> int:
    all_slugs = _opted_in_repository_slugs()
    if not all_slugs:
        return 0
    all_roots = _opted_in_repository_roots(all_slugs)
    if not all_roots:
        return 0
    session_id = hook_input.get(SESSION_ID_KEY)
    _log(
        RUN_DIAGNOSTIC_TEMPLATE.format(
            event=hook_event_name, stop_hook_active=hook_input.get(STOP_HOOK_ACTIVE_KEY)
        )
    )
    if hook_event_name == PROMPT_EVENT_NAME:
        _record_prompt_baselines(session_id, all_roots, hook_input.get(PROMPT_KEY))
        return 0
    block_reason = _turn_block_reason(session_id, all_roots)
    if block_reason is None:
        return 0
    log_hook_block(Path(__file__).name, STOP_EVENT_NAME, block_reason)
    return hold_stop(hook_input, block_reason)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return 0
    if os.environ.get(REVIEW_CHILD_ENVIRONMENT_VARIABLE) == REVIEW_CHILD_MARKER:
        return 0
    hook_event_name = hook_input.get(HOOK_EVENT_NAME_KEY)
    if hook_event_name == STOP_EVENT_NAME:
        run_budget_seconds = STOP_RUN_BUDGET_SECONDS
    elif hook_event_name == PROMPT_EVENT_NAME:
        run_budget_seconds = PROMPT_RUN_BUDGET_SECONDS
    else:
        return 0
    with time_budget(run_budget_seconds):
        return _handle_event(hook_input, hook_event_name)


if __name__ == "__main__":
    sys.exit(main())
