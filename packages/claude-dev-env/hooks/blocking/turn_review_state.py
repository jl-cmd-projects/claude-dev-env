"""Keep the session's review state, its file lock and the log for the turn review gate.

Each session has one state file in the temp folder. It holds the snapshot each
checkout was last reviewed up to, the hold count, and every finding by its id::

    turn-review-<session>.json
        {"baselines": {"/work/app": "<snapshot B>"}, "blocks_in_a_row": 1,
         "findings": {"TR-1": {"text": "src/service.py:3 - ...", "status": "open"}}}

A saved entry in another form is left out on load, such as a baseline that is
not a commit name or a finding with an unknown status. A state file that
cannot be read gives an empty state. A save that fails writes one log line.

The lock functions take and release a lock on an open file, with ``msvcrt`` on
Windows and ``fcntl`` on other systems. ``_log`` adds one dated line to
``~/.claude/logs/turn-review.log``. A line that cannot be written is dropped.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from atomic_file_writer import write_text_atomically
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.session_file_id import session_file_id
from hooks_constants.turn_review_gate_constants import (
    ALL_FINDING_STATUSES,
    ALL_LOG_PATH_PARTS,
    BASELINE_COMMIT_PATTERN,
    FINDING_BASE_KEY,
    FINDING_ID_PATTERN,
    FINDING_ID_TEMPLATE,
    FINDING_JUDGE_REASON_KEY,
    FINDING_REPOSITORY_KEY,
    FINDING_STATUS_KEY,
    FINDING_STATUS_OPEN,
    FINDING_TEXT_KEY,
    FINDING_TURN_KEY,
    LOG_LINE_TEMPLATE,
    LOG_TEXT_ENCODING,
    LOG_UNENCODABLE_HANDLER,
    STATE_BASELINES_KEY,
    STATE_BLOCKS_KEY,
    STATE_FILE_TEMPLATE,
    STATE_FINDINGS_KEY,
    STATE_LAST_WAKE_KEY,
    STATE_LOCK_BYTE_COUNT,
    STATE_OPEN_TURN_PROMPT_KEY,
    STATE_SAVE_FAILURE_DIAGNOSTIC_TEMPLATE,
    STATE_TEMPORARY_PREFIX,
    STATE_TEXT_ENCODING,
    STATE_TURN_OPEN_KEY,
)


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


def _release_and_close(file_descriptor: int, is_locked: bool) -> None:
    try:
        if is_locked:
            _release_file_lock(file_descriptor)
    finally:
        os.close(file_descriptor)


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
