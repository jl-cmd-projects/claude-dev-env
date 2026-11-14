#!/usr/bin/env python3
"""Stop hook that has a fresh reviewer read each turn's changes, and a judge rule on each dismissal.

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

Each finding gets an id that is unique in the session, such as ``TR-1``, and
is saved as open in the session's state. The wake shows the id beside the
finding. The agent fixes the finding or contests it with one reply line, and
a separate judge run decides::

    reply ends with "Dismiss TR-1: the caller retries the update"
    stop            ->  claude -p --model sonnet --effort high, prompt on stdin
    judge approves  ->  TR-1 dismissed, reason saved, one log line, no wake
    judge rejects   ->  TR-1 upheld; exit 2: "Dismissal of TR-1 rejected: <reason>. Fix it."

The reply comes from ``last_assistant_message`` in the Stop input, or from
the text of the last assistant message in ``transcript_path`` when that field
is missing. The judge gets the checkout path and one JSON object of data::

    {"requests": [{"id": "TR-1", "commit_range": "A..B",
                   "finding": "src/service.py:3 - ...", "reason_to_dismiss": "..."}],
     "user_messages": ["the last five messages the user typed, cut to 2000 characters"]}

The user's messages come from ``transcript_path``. Only entries with
``origin.kind`` ``human`` count, and text that starts with ``<`` is left out. The judge gets no other part of the
conversation. It runs with the review's read-only options, once per checkout
that holds a contested finding. A rejection counts toward the hold count, and
it shares one wake with that stop's new findings. The judge runs after the
review and shares its time. A judge that fails, times out or gets no time, or
whose whole answer is not one JSON array of verdicts, leaves the finding open
and exits 0 with no output. A ``Dismiss`` line for an id that is not open, or
one sent at the hold cap, is logged and not judged.

Claude Code runs the Stop entry with ``asyncRewake``. A plain ``claude -p``
run has no background, so the same entry holds that stop with exit code 2.
A finding or a rejected dismissal goes to stderr and to the stdout ``reason``. Every
other outcome exits 0 with no output, and its diagnostic goes to ``~/.claude/logs/turn-review.log``.

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
through when the review fails or times out. A stop below the cap with no
finding, no rejection and no dismissal to judge resets the count, and so does a user's prompt. A prompt within 10 seconds
of the last wake, or one that starts with ``<task-notification``, belongs to
the wake and keeps the count, so a chain of wakes stops at three.
A stop gets 280 seconds of work and a prompt 25, under the 300 and 30
second registrations. A git call or review that would start after that time
is skipped.
The cap and the file limit match Anthropic's security-guidance plugin. The review and judge
runs carry ``CLAUDE_TURN_REVIEW_CHILD=1`` and none of the parent session's id,
messaging or ingress variables, and the hook does nothing inside such a run. Each may read
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
    ALL_FINDING_STATUSES,
    ALL_LOG_PATH_PARTS,
    ALL_PARENT_SESSION_VARIABLES,
    ALL_REVIEW_ALLOWED_TOOLS,
    ALL_REVIEW_DISALLOWED_TOOLS,
    BASELINE_COMMIT_PATTERN,
    BLOCK_REASON_TEMPLATE,
    DISMISS_AT_CAP_DIAGNOSTIC_TEMPLATE,
    DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE,
    FINDING_BASE_KEY,
    FINDING_DISMISSED_DIAGNOSTIC_TEMPLATE,
    FINDING_ID_PATTERN,
    FINDING_ID_TEMPLATE,
    FINDING_JUDGE_REASON_KEY,
    FINDING_LINE_WITH_ID_TEMPLATE,
    FINDING_REPOSITORY_KEY,
    FINDING_STATUS_DISMISSED,
    FINDING_STATUS_KEY,
    FINDING_STATUS_OPEN,
    FINDING_STATUS_UPHELD,
    FINDING_TEXT_KEY,
    FINDING_TURN_KEY,
    FINDING_UPHELD_DIAGNOSTIC_TEMPLATE,
    JUDGE_EFFORT,
    JUDGE_FAILURE_DIAGNOSTIC_TEMPLATE,
    JUDGE_MODEL_ALIAS,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_COMMIT_RANGE_TEMPLATE,
    JUDGE_DATA_INDENT,
    JUDGE_DATA_REQUESTS_KEY,
    JUDGE_DATA_USER_MESSAGES_KEY,
    JUDGE_ID_KEY,
    JUDGE_REQUEST_FINDING_KEY,
    JUDGE_REQUEST_RANGE_KEY,
    JUDGE_REQUEST_REASON_KEY,
    ALL_TRANSCRIPT_NOT_TYPED_FLAGS,
    MAXIMUM_USER_MESSAGE_CHARACTERS,
    NESTED_TOO_DEEP_REASON,
    TRANSCRIPT_HUMAN_ORIGIN_KIND,
    TRANSCRIPT_MARKUP_START,
    TRANSCRIPT_MESSAGE_ID_KEY,
    TRANSCRIPT_ORIGIN_KEY,
    TRANSCRIPT_ORIGIN_KIND_KEY,
    TRANSCRIPT_UNREADABLE_DIAGNOSTIC_TEMPLATE,
    TRANSCRIPT_USER_TYPE,
    USER_MESSAGE_COUNT,
    NO_VERDICT_DIAGNOSTIC_TEMPLATE,
    OUTSIDE_REPOSITORY_LABEL,
    REJECTION_LINE_SEPARATOR,
    REJECTION_LINE_TEMPLATE,
    REPLY_TEXT_KEY,
    SENTENCE_END_CHARACTERS,
    STATE_FINDINGS_KEY,
    TRANSCRIPT_ASSISTANT_TYPE,
    TRANSCRIPT_BLOCK_TYPE_KEY,
    TRANSCRIPT_CONTENT_KEY,
    TRANSCRIPT_ENTRY_TYPE_KEY,
    TRANSCRIPT_MESSAGE_KEY,
    TRANSCRIPT_PATH_KEY,
    TRANSCRIPT_TEXT_BLOCK_TYPE,
    TRANSCRIPT_TEXT_ENCODING,
    TRANSCRIPT_TEXT_KEY,
    TRANSCRIPT_TEXT_SEPARATOR,
    UNKNOWN_FINDING_LABEL,
    WAKE_PART_SEPARATOR,
    WORD_SEPARATOR,
    FINDING_LINE_SEPARATOR,
    GIT_DIRECTORY_NAME,
    HOOK_EVENT_NAME_KEY,
    LOG_LINE_TEMPLATE,
    LOG_TEXT_ENCODING,
    LOG_UNENCODABLE_HANDLER,
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
from turn_review_findings import JudgeVerdict, dismiss_requests, finding_lines, judge_verdicts
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
        with log_path.open(
            "a", encoding=LOG_TEXT_ENCODING, errors=LOG_UNENCODABLE_HANDLER
        ) as log_file:
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
        *_read_only_child_options(),
    ]


def _judge_command() -> list[str]:
    return [
        shutil.which(REVIEW_EXECUTABLE_NAME) or REVIEW_EXECUTABLE_NAME,
        "-p",
        "--model",
        JUDGE_MODEL_ALIAS,
        "--effort",
        JUDGE_EFFORT,
        *_read_only_child_options(),
    ]


def _read_only_child_options() -> list[str]:
    return [
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


@dataclass(frozen=True)
class _ChildRun:
    repository_root: Path
    all_command_parts: list[str]
    prompt_text: str | None
    failure_template: str

    def write_failure(self, failure_text: str) -> None:
        _log(
            self.failure_template.format(
                repository=self.repository_root.name, reason=failure_text
            )
        )


def _child_stdout(child_run: _ChildRun, remaining_seconds: float) -> str | None:
    closed_stdin = subprocess.DEVNULL if child_run.prompt_text is None else None
    try:
        completed_process = subprocess.run(
            child_run.all_command_parts,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=remaining_seconds,
            cwd=str(child_run.repository_root),
            env=_review_environment(),
            creationflags=hidden_window_creation_flags(),
            stdin=closed_stdin,
            input=child_run.prompt_text,
        )
    except subprocess.TimeoutExpired:
        child_run.write_failure("timed out")
        return None
    except OSError as start_error:
        child_run.write_failure(str(start_error))
        return None
    if completed_process.returncode != 0:
        child_run.write_failure(f"exit {completed_process.returncode}")
        return None
    return completed_process.stdout


def _child_result_text(child_run: _ChildRun, deadline: float) -> str | None:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds < MINIMUM_REVIEW_SECONDS:
        child_run.write_failure("no time left this stop")
        return None
    child_stdout = _child_stdout(child_run, remaining_seconds)
    if child_stdout is None:
        return None
    try:
        child_result = json.loads(child_stdout)
    except (ValueError, RecursionError):
        child_run.write_failure("output was not JSON")
        return None
    result_text = child_result.get(REVIEW_RESULT_KEY) if isinstance(child_result, dict) else None
    if not isinstance(result_text, str):
        child_run.write_failure("output had no result text")
        return None
    return result_text


def _review_text(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    review_run = _ChildRun(
        repository_root,
        _review_command(base_commit, turn_commit),
        None,
        REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    )
    return _child_result_text(review_run, review_deadline)


def _state_path(session_id: object) -> Path:
    return Path(tempfile.gettempdir()) / STATE_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )


@dataclass
class _Finding:
    text: str
    repository: str
    base_commit: str
    turn_commit: str
    status: str = FINDING_STATUS_OPEN
    judge_reason: str | None = None


@dataclass
class _ReviewState:
    all_baselines: dict[str, str] = field(default_factory=dict)
    blocks_in_a_row: int = 0
    is_turn_open: bool = False
    last_wake_at: float | None = None
    open_turn_prompt_at: float | None = None
    all_findings: dict[str, _Finding] = field(default_factory=dict)


def _saved_time(raw_value: object) -> float | None:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return None
    return float(raw_value)


def _is_commit_name(raw_value: object) -> bool:
    return isinstance(raw_value, str) and re.fullmatch(BASELINE_COMMIT_PATTERN, raw_value) is not None


def _saved_finding(raw_entry: object) -> _Finding | None:
    if not isinstance(raw_entry, dict):
        return None
    text = raw_entry.get(FINDING_TEXT_KEY)
    repository = raw_entry.get(FINDING_REPOSITORY_KEY)
    base_commit = raw_entry.get(FINDING_BASE_KEY)
    turn_commit = raw_entry.get(FINDING_TURN_KEY)
    status = raw_entry.get(FINDING_STATUS_KEY)
    judge_reason = raw_entry.get(FINDING_JUDGE_REASON_KEY)
    if not (
        isinstance(text, str)
        and isinstance(repository, str)
        and _is_commit_name(base_commit)
        and _is_commit_name(turn_commit)
        and status in ALL_FINDING_STATUSES
    ):
        return None
    return _Finding(
        text,
        repository,
        str(base_commit),
        str(turn_commit),
        str(status),
        judge_reason if isinstance(judge_reason, str) else None,
    )


def _saved_findings(raw_findings: object) -> dict[str, _Finding]:
    if not isinstance(raw_findings, dict):
        return {}
    all_findings: dict[str, _Finding] = {}
    for each_id, each_entry in raw_findings.items():
        saved_finding = _saved_finding(each_entry)
        if isinstance(each_id, str) and re.fullmatch(FINDING_ID_PATTERN, each_id) and saved_finding:
            all_findings[each_id] = saved_finding
    return all_findings


def _finding_number(finding_id: str) -> int:
    id_match = re.fullmatch(FINDING_ID_PATTERN, finding_id)
    return int(id_match.group(1)) if id_match else 0


def _next_finding_id(review_state: _ReviewState) -> str:
    highest_number = max(map(_finding_number, review_state.all_findings), default=0)
    return FINDING_ID_TEMPLATE.format(number=highest_number + 1)


def _finding_record(finding: _Finding) -> dict[str, str | None]:
    return {
        FINDING_TEXT_KEY: finding.text,
        FINDING_REPOSITORY_KEY: finding.repository,
        FINDING_BASE_KEY: finding.base_commit,
        FINDING_TURN_KEY: finding.turn_commit,
        FINDING_STATUS_KEY: finding.status,
        FINDING_JUDGE_REASON_KEY: finding.judge_reason,
    }


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
        if isinstance(each_root, str) and _is_commit_name(each_commit)
    }
    raw_blocks = saved_state.get(STATE_BLOCKS_KEY)
    return _ReviewState(
        all_baselines,
        raw_blocks if isinstance(raw_blocks, int) else 0,
        saved_state.get(STATE_TURN_OPEN_KEY) is True,
        _saved_time(saved_state.get(STATE_LAST_WAKE_KEY)),
        _saved_time(saved_state.get(STATE_OPEN_TURN_PROMPT_KEY)),
        _saved_findings(saved_state.get(STATE_FINDINGS_KEY)),
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
                    STATE_FINDINGS_KEY: {
                        each_id: _finding_record(each_finding)
                        for each_id, each_finding in review_state.all_findings.items()
                    },
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
) -> list[str] | None:
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
    return finding_lines(review_text or "", all_changed_paths) or None


@dataclass(frozen=True)
class _JudgeRequest:
    finding_id: str
    finding: _Finding
    reason: str


@dataclass(frozen=True)
class _StopClaim:
    all_turn_ranges: list[tuple[Path, str, str]] = field(default_factory=list)
    all_judge_requests: list[_JudgeRequest] = field(default_factory=list)


def _reversed_transcript_entries(hook_input: dict) -> Iterator[dict]:
    transcript_path = hook_input.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    try:
        all_transcript_lines = Path(transcript_path).read_text(
            encoding=TRANSCRIPT_TEXT_ENCODING, errors="replace"
        ).splitlines()
    except OSError:
        return
    for each_line in reversed(all_transcript_lines):
        try:
            transcript_entry = json.loads(each_line)
        except ValueError:
            continue
        except RecursionError:
            _log(TRANSCRIPT_UNREADABLE_DIAGNOSTIC_TEMPLATE.format(reason=NESTED_TOO_DEEP_REASON))
            continue
        if isinstance(transcript_entry, dict):
            yield transcript_entry


class _ReversedTranscript:
    """The transcript's entries, newest first, with each line decoded once per stop."""

    def __init__(self, hook_input: dict) -> None:
        self._unread_entries = _reversed_transcript_entries(hook_input)
        self._all_read_entries: list[dict] = []

    def __iter__(self) -> Iterator[dict]:
        yield from self._all_read_entries
        for each_entry in self._unread_entries:
            self._all_read_entries.append(each_entry)
            yield each_entry


def _entry_message(transcript_entry: dict) -> dict:
    message = transcript_entry.get(TRANSCRIPT_MESSAGE_KEY)
    return message if isinstance(message, dict) else {}


def _entry_text(transcript_entry: dict) -> str:
    content = _entry_message(transcript_entry).get(TRANSCRIPT_CONTENT_KEY)
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return TRANSCRIPT_TEXT_SEPARATOR.join(
        each_block[TRANSCRIPT_TEXT_KEY]
        for each_block in content
        if isinstance(each_block, dict)
        and each_block.get(TRANSCRIPT_BLOCK_TYPE_KEY) == TRANSCRIPT_TEXT_BLOCK_TYPE
        and isinstance(each_block.get(TRANSCRIPT_TEXT_KEY), str)
    ).strip()


def _is_assistant_entry(transcript_entry: dict) -> bool:
    return transcript_entry.get(TRANSCRIPT_ENTRY_TYPE_KEY) == TRANSCRIPT_ASSISTANT_TYPE


def _last_assistant_message_text(transcript: _ReversedTranscript) -> str:
    all_text_parts: list[str] = []
    last_message_id: object = None
    for each_entry in transcript:
        is_first_assistant_entry = not all_text_parts and last_message_id is None
        if is_first_assistant_entry and not _is_assistant_entry(each_entry):
            continue
        message_id = _entry_message(each_entry).get(TRANSCRIPT_MESSAGE_ID_KEY)
        if not is_first_assistant_entry and (
            not _is_assistant_entry(each_entry) or message_id != last_message_id
        ):
            break
        all_text_parts.append(_entry_text(each_entry))
        if message_id is None:
            break
        last_message_id = message_id
    return TRANSCRIPT_TEXT_SEPARATOR.join(reversed(all_text_parts)).strip()


def _reply_text(hook_input: dict, transcript: _ReversedTranscript) -> str:
    reply_text = hook_input.get(REPLY_TEXT_KEY)
    if isinstance(reply_text, str):
        return reply_text
    return _last_assistant_message_text(transcript)


def _typed_user_text(transcript_entry: dict) -> str:
    if transcript_entry.get(TRANSCRIPT_ENTRY_TYPE_KEY) != TRANSCRIPT_USER_TYPE:
        return ""
    if any(transcript_entry.get(each_flag) for each_flag in ALL_TRANSCRIPT_NOT_TYPED_FLAGS):
        return ""
    origin = transcript_entry.get(TRANSCRIPT_ORIGIN_KEY)
    if (
        not isinstance(origin, dict)
        or origin.get(TRANSCRIPT_ORIGIN_KIND_KEY) != TRANSCRIPT_HUMAN_ORIGIN_KIND
    ):
        return ""
    typed_text = _entry_text(transcript_entry)
    return "" if typed_text.startswith(TRANSCRIPT_MARKUP_START) else typed_text


def _typed_user_messages(transcript: _ReversedTranscript) -> list[str]:
    all_messages: list[str] = []
    for each_entry in transcript:
        typed_text = _typed_user_text(each_entry)
        if typed_text:
            all_messages.append(typed_text[:MAXIMUM_USER_MESSAGE_CHARACTERS])
        if len(all_messages) == USER_MESSAGE_COUNT:
            break
    return list(reversed(all_messages))


def _judge_requests(
    review_state: _ReviewState,
    all_dismiss_reasons: dict[str, str],
    all_roots: list[Path],
    is_capped: bool,
) -> list[_JudgeRequest]:
    all_root_names = {str(each_root) for each_root in all_roots}
    all_requests: list[_JudgeRequest] = []
    for each_id, each_reason in all_dismiss_reasons.items():
        finding = review_state.all_findings.get(each_id)
        skip_diagnostic = _dismiss_skip_diagnostic(each_id, finding, all_root_names, is_capped)
        if skip_diagnostic is not None:
            _log(skip_diagnostic)
            continue
        if finding is not None:
            all_requests.append(_JudgeRequest(each_id, finding, each_reason))
    return all_requests


def _dismiss_skip_diagnostic(
    finding_id: str, finding: _Finding | None, all_root_names: set[str], is_capped: bool
) -> str | None:
    if finding is None:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=UNKNOWN_FINDING_LABEL
        )
    if finding.status != FINDING_STATUS_OPEN:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=finding.status
        )
    if finding.repository not in all_root_names:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=OUTSIDE_REPOSITORY_LABEL
        )
    if is_capped:
        return DISMISS_AT_CAP_DIAGNOSTIC_TEMPLATE.format(finding_id=finding_id)
    return None


def _claim_locked_stop(
    session_id: object, all_roots: list[Path], all_dismiss_reasons: dict[str, str]
) -> _StopClaim:
    review_state = _load_state(session_id)
    is_capped = review_state.blocks_in_a_row >= MAXIMUM_BLOCKS_IN_A_ROW
    all_judge_requests = _judge_requests(review_state, all_dismiss_reasons, all_roots, is_capped)
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
    if not all_turn_ranges and not all_judge_requests and not is_capped:
        review_state.blocks_in_a_row = 0
    review_state.all_baselines = all_next_baselines
    review_state.is_turn_open = (
        review_state.open_turn_prompt_at is not None
        and time.time() - review_state.open_turn_prompt_at < RACING_STOP_WINDOW_SECONDS
    )
    review_state.open_turn_prompt_at = None
    _save_state(session_id, review_state)
    return _StopClaim(all_turn_ranges, all_judge_requests)


def _claim_stop(
    session_id: object, all_roots: list[Path], all_dismiss_reasons: dict[str, str]
) -> _StopClaim:
    with _state_lock(session_id, STATE_LOCK_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return _StopClaim()
        return _claim_locked_stop(session_id, all_roots, all_dismiss_reasons)


def _judge_prompt(
    repository_root: Path, all_requests: list[_JudgeRequest], all_user_messages: list[str]
) -> str:
    judge_data = {
        JUDGE_DATA_REQUESTS_KEY: [
            {
                JUDGE_ID_KEY: each_request.finding_id,
                JUDGE_REQUEST_RANGE_KEY: JUDGE_COMMIT_RANGE_TEMPLATE.format(
                    base_commit=each_request.finding.base_commit,
                    turn_commit=each_request.finding.turn_commit,
                ),
                JUDGE_REQUEST_FINDING_KEY: each_request.finding.text,
                JUDGE_REQUEST_REASON_KEY: each_request.reason,
            }
            for each_request in all_requests
        ],
        JUDGE_DATA_USER_MESSAGES_KEY: all_user_messages,
    }
    return JUDGE_PROMPT_TEMPLATE.format(
        repository=repository_root,
        user_message_characters=MAXIMUM_USER_MESSAGE_CHARACTERS,
        judge_data=json.dumps(judge_data, indent=JUDGE_DATA_INDENT, ensure_ascii=True),
    )


def _repository_verdicts(
    repository_root: Path,
    all_requests: list[_JudgeRequest],
    all_user_messages: list[str],
    deadline: float,
) -> dict[str, JudgeVerdict]:
    judge_run = _ChildRun(
        repository_root,
        _judge_command(),
        _judge_prompt(repository_root, all_requests, all_user_messages),
        JUDGE_FAILURE_DIAGNOSTIC_TEMPLATE,
    )
    result_text = _child_result_text(judge_run, deadline)
    if result_text is None:
        return {}
    all_requested_ids = [each_request.finding_id for each_request in all_requests]
    all_verdicts = judge_verdicts(result_text, all_requested_ids)
    if all_verdicts is None:
        judge_run.write_failure("answer was not one JSON array of verdicts")
        return {}
    for each_id in all_requested_ids:
        if each_id not in all_verdicts:
            _log(NO_VERDICT_DIAGNOSTIC_TEMPLATE.format(finding_id=each_id))
    return all_verdicts


def _all_judge_verdicts(
    all_requests: list[_JudgeRequest],
    all_roots: list[Path],
    all_user_messages: list[str],
    deadline: float,
) -> dict[str, JudgeVerdict]:
    all_verdicts: dict[str, JudgeVerdict] = {}
    for each_root in all_roots:
        all_root_requests = [
            each_request
            for each_request in all_requests
            if each_request.finding.repository == str(each_root)
        ]
        if all_root_requests:
            all_verdicts.update(
                _repository_verdicts(each_root, all_root_requests, all_user_messages, deadline)
            )
    return all_verdicts


def _one_line(judge_reason: str) -> str:
    return WORD_SEPARATOR.join(judge_reason.split())


def _one_sentence(judge_reason: str) -> str:
    return _one_line(judge_reason).rstrip(SENTENCE_END_CHARACTERS)


def _apply_verdicts(
    review_state: _ReviewState, all_verdicts: dict[str, JudgeVerdict]
) -> list[str]:
    all_rejection_lines: list[str] = []
    for each_id in sorted(all_verdicts, key=_finding_number):
        finding = review_state.all_findings.get(each_id)
        if finding is None or finding.status != FINDING_STATUS_OPEN:
            continue
        verdict = all_verdicts[each_id]
        finding.judge_reason = verdict.reason
        if verdict.is_approved:
            finding.status = FINDING_STATUS_DISMISSED
            _log(
                FINDING_DISMISSED_DIAGNOSTIC_TEMPLATE.format(
                    finding_id=each_id, reason=_one_line(verdict.reason)
                )
            )
            continue
        finding.status = FINDING_STATUS_UPHELD
        _log(
            FINDING_UPHELD_DIAGNOSTIC_TEMPLATE.format(
                finding_id=each_id, reason=_one_line(verdict.reason)
            )
        )
        all_rejection_lines.append(
            REJECTION_LINE_TEMPLATE.format(
                finding_id=each_id, reason=_one_sentence(verdict.reason)
            )
        )
    return all_rejection_lines


def _record_new_findings(
    review_state: _ReviewState, all_repository_findings: list[tuple[Path, str, str, list[str]]]
) -> list[str]:
    all_repository_blocks: list[str] = []
    for each_root, each_base_commit, each_turn_commit, each_finding_lines in all_repository_findings:
        all_lines_with_ids: list[str] = []
        for each_line in each_finding_lines:
            finding_id = _next_finding_id(review_state)
            review_state.all_findings[finding_id] = _Finding(
                each_line, str(each_root), each_base_commit, each_turn_commit
            )
            all_lines_with_ids.append(
                FINDING_LINE_WITH_ID_TEMPLATE.format(finding_id=finding_id, finding=each_line)
            )
        all_repository_blocks.append(
            REPOSITORY_FINDINGS_TEMPLATE.format(
                repository=each_root.name,
                findings=FINDING_LINE_SEPARATOR.join(all_lines_with_ids),
            )
        )
    return all_repository_blocks


def _locked_stop_wake(
    session_id: object,
    all_repository_findings: list[tuple[Path, str, str, list[str]]],
    all_verdicts: dict[str, JudgeVerdict],
) -> str | None:
    review_state = _load_state(session_id)
    all_wake_parts: list[str] = []
    all_rejection_lines = _apply_verdicts(review_state, all_verdicts)
    if all_rejection_lines:
        all_wake_parts.append(REJECTION_LINE_SEPARATOR.join(all_rejection_lines))
    all_repository_blocks = _record_new_findings(review_state, all_repository_findings)
    if all_repository_blocks:
        all_wake_parts.append(
            BLOCK_REASON_TEMPLATE.format(
                all_findings=REPOSITORY_FINDINGS_SEPARATOR.join(all_repository_blocks)
            )
        )
    if all_wake_parts:
        review_state.blocks_in_a_row += 1
        review_state.last_wake_at = time.time()
    elif review_state.blocks_in_a_row < MAXIMUM_BLOCKS_IN_A_ROW:
        review_state.blocks_in_a_row = 0
    _save_state(session_id, review_state)
    return WAKE_PART_SEPARATOR.join(all_wake_parts) or None


def _saved_stop_wake(
    session_id: object,
    all_repository_findings: list[tuple[Path, str, str, list[str]]],
    all_verdicts: dict[str, JudgeVerdict],
) -> str | None:
    with _state_lock(session_id, STATE_LOCK_OUTCOME_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return None
        return _locked_stop_wake(session_id, all_repository_findings, all_verdicts)


def _turn_block_reason(
    session_id: object, all_roots: list[Path], hook_input: dict | None = None
) -> str | None:
    stop_input = hook_input or {}
    transcript = _ReversedTranscript(stop_input)
    stop_claim = _claim_stop(
        session_id, all_roots, dismiss_requests(_reply_text(stop_input, transcript))
    )
    if not stop_claim.all_turn_ranges and not stop_claim.all_judge_requests:
        return None
    all_repository_findings: list[tuple[Path, str, str, list[str]]] = []
    deadline = time.monotonic() + min(REVIEW_TIMEOUT_SECONDS, remaining_seconds())
    for each_root, each_base_commit, each_turn_commit in stop_claim.all_turn_ranges:
        all_lines = _repository_findings(each_root, each_base_commit, each_turn_commit, deadline)
        if all_lines:
            all_repository_findings.append(
                (each_root, each_base_commit, each_turn_commit, all_lines)
            )
    all_user_messages = (
        _typed_user_messages(transcript) if stop_claim.all_judge_requests else []
    )
    all_verdicts = _all_judge_verdicts(
        stop_claim.all_judge_requests, all_roots, all_user_messages, deadline
    )
    return _saved_stop_wake(session_id, all_repository_findings, all_verdicts)


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
    block_reason = _turn_block_reason(session_id, all_roots, hook_input)
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
