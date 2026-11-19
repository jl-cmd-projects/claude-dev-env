#!/usr/bin/env python3
"""Stop hook that ends a working reply with an In progress footer or a question card round.

The gate holds the stop for these shapes, and only in a session it covers::

    hold:  "I deferred the backoff setting."        no question card after it
    hold:  "Nothing is deferred."                   a marker line; negation does not cancel it
    allow: a marker line, then an answered AskUserQuestion call
    allow: an Edit call, then "Done."               nothing in progress, no closing line owed
    hold:  an Edit call, then "Done."               task #28 in_progress: the footer is owed
    allow: an Edit call, then the footer naming task #28
    allow: the footer naming #28, a later Bash call, then "Read it."   no typed prompt or card between
    hold:  the footer that names #28 and leaves out in-progress task #29
    hold:  "Open items: none." beside task #28 in_progress

The stretch is every top-level record after the last question call that
reached the user, then the payload's closing reply. The closing reply is the
newest text after the last work call. Each reply's In progress footer, as
``closing_question_round_footer.split_footer`` reads it, is scanned with the
status markers "pending", "blocked", "not done", and "not run" left out, so a
footer may say where work stands while a question, a deferral, or an ask of
the user in it still counts. A marker line is a prose
line ``closing_question_round_open_items`` finds in the texts: a marker word or
a line that ends with a question mark. Work is any tool call that is no
question call and that sits in the stretch after the last record whose final
text ends with the footer, in a record with no work call of its own. Work is
in progress when the session's task list, as ``closing_question_round_tasks``
reads it, holds an ``in_progress`` task, or the payload's ``background_tasks``
is a non-empty list, object, or string.

- A marker line holds the stop with the closing round reason, unless
  background work runs. The reason quotes the last 8 marker lines at most,
  each cut to 160 characters, and counts the earlier ones. Three dots in
  backticks stand where a code span sat.
- A closing reply with no footer that ends with the old declaration ``Open
  items: none.`` beside an in-progress task holds the stop.
- Work with work in progress and no footer holds the stop, unless a reply
  since the later of the last typed prompt and the last question call that
  reached the user already ended with a footer that still shows the work, as
  ``is_footer_still_current`` reads it. The user saw that footer, so it is
  not sent again.
- A footer that leaves out an in-progress task holds the stop, as
  ``closing_question_round_footer.left_out_tasks`` matches the tasks.
- Nothing in progress and no background work: the reply owes no closing line.

The gate leaves a stop alone, with exit code 0 and no output, when:

- the payload cannot be read, or it carries a non-empty ``agent_id`` (a
  subagent) or a ``conversation_id`` (Cursor);
- ``CLAUDE_CODE_SESSION_ATTENDED`` is ``0`` (a headless run);
- the session turned the gate off: a prompt that held ``--nocards`` set the
  session's flag, and a later prompt with it clears the flag again, as
  ``session/closing_question_gate_bypass.py`` describes;
- the transcript is missing or cannot be read;
- no person started the session. A record that carries ``turnOrigin`` equal to
  ``human`` and starts a turn, as ``claude_prompt_text`` reads it, is a prompt
  a person typed. When no record carries a ``turnOrigin`` key, any record that
  starts a turn counts when ``CLAUDE_CODE_SESSION_ATTENDED`` is ``1``;
- this gate already held twice since the later of the last typed prompt and
  the last question call that reached the user. A hold is a ``user`` record
  whose text starts with "Stop hook feedback" and carries the first sentence
  of any of its reasons within its first 200 characters;
- the payload is over 16 MiB, which the gate does not parse;
- 7 seconds pass on a monotonic clock, checked before each transcript line
  read, and before each text, paragraph, line, and marker scan window;
- 8 seconds pass, counted from the start of the stdin read. The check runs in
  a child process, which is killed then, and a watchdog thread ends a stdin
  read that never finishes at 8.5 seconds;
- the child exits with a code other than 0 or 2;
- stdin, stdout, or stderr is closed;
- stdout or stderr cannot be written, or the write has not finished 1
  second after it starts;
- any step raises.

A transcript line over 16 MiB or a text over 2 MiB is skipped. The gate does
not read ``stop_hook_active``. The closing round reason tells the agent to
read the task list, its notes, and the live state of each item, to keep the
turn's chat text inside the limit ``question_brief_gate.py`` counts, and to
send each item as its own ``AskUserQuestion`` question. Each footer reason
lists the in-progress tasks with their key words and asks for a footer in
plain words for the user. A hold exits with code 2 and writes the reason to
stdout and stderr.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from closing_question_gate_flag import is_bypass_on
from closing_question_round_footer import footer_reason, left_out_tasks, split_footer
from closing_question_round_lines import transcript_lines
from closing_question_round_open_items import declares_no_open_items, marked_open_lines
from closing_question_round_tasks import SessionTasks, session_tasks
from closing_question_round_transcript import (
    _message_id,
    block_texts,
    has_work_call,
    is_same_reply,
    last_typed_prompt_position,
    reply_lines,
    last_written_reply,
    payload_closing_texts,
    stretch_start,
    top_level_records,
)
from open_tasks_transcript_records import _content_blocks, is_assistant_record

from hooks_constants.closing_question_round_gate_constants import (
    ALL_REASON_LEADS,
    BACKGROUND_TASKS_KEY,
    CLIPPED_LINE_END,
    CLOSING_ROUND_INSTRUCTION,
    CLOSING_ROUND_REASON_LEAD,
    CODE_SPAN_SHOWN_TEXT,
    DECISION_PROCESS_FLAG,
    FEEDBACK_OPENING_LENGTH,
    FOOTER_GAP_REASON_LEAD,
    FOOTER_MISSING_REASON_LEAD,
    FOOTER_CHANGED_REASON_LEAD,
    HEADLESS_SESSION_ATTENDED_TEXT,
    IN_PROGRESS_TASKS_REASON_LEAD,
    MAXIMUM_HOLD_COUNT,
    MAXIMUM_PAYLOAD_BYTES,
    MAXIMUM_QUOTED_LINE_COUNT,
    MAXIMUM_QUOTED_LINE_LENGTH,
    OPEN_ITEM_LINES_LABEL,
    OUTPUT_WATCHDOG_SECONDS,
    QUOTED_LINE_TEMPLATE,
    REASON_PART_SEPARATOR,
    SCANNED_PARAGRAPH_SEPARATOR,
    FOOTER_STATUS_MARKER_PATTERN,
    FOOTER_STATUS_STAND_IN,
    REMAINING_LINES_TEMPLATE,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    STDIN_WATCHDOG_SECONDS,
    ALL_BACKGROUND_JOB_ID_KEYS,
    FOOTER_JOBS_DIGEST_LENGTH,
    FOOTER_JOBS_FILE_MODE,
    FOOTER_JOBS_TEMP_SUFFIX,
    FOOTER_SNAPSHOT_KEPT_COUNT,
    FOOTER_SNAPSHOT_LINE_SEPARATOR,
    FOOTER_SNAPSHOT_PART_COUNT,
    NO_REPLY_KEY,
    REPLY_PART_JOINER,
    FOOTER_SNAPSHOT_PENDING_MARK,
    FOOTER_SNAPSHOT_SENT_MARK,
    FOOTER_SNAPSHOT_SEPARATOR,
    FOOTER_JOBS_FILE_TEMPLATE,
    FOOTER_JOBS_READ_LIMIT,
    FOOTER_JOBS_TEXT_ENCODING,
    NO_FOLLOW_FLAG,
    FOOTER_JOBS_KEY_TEMPLATE,
    LAST_ASSISTANT_MESSAGE_KEY,
    FOOTER_JOBS_MARKER_NAME,
    SESSION_ID_KEY,
    STOP_DEADLINE_SECONDS,
    SUBAGENT_ID_KEY,
    WATCHDOG_GRACE_SECONDS,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.session_file_id import session_file_id
from hooks_constants.setup_project_paths_constants import UTF8_BYTE_ORDER_MARK
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    CONTENT_KEY,
    CURSOR_CONVERSATION_ID_KEY,
    HOOK_EVENT_NAME,
    MESSAGE_KEY,
    RECORD_TYPE_KEY,
    STOP_HOOK_FEEDBACK_PREFIX,
    TOOL_USE_BLOCK_TYPE,
    TRANSCRIPT_PATH_KEY,
    USER_RECORD_TYPE,
    WORD_SEPARATOR,
)
from hooks_constants.stop_hook_hold import hold_stop
from hooks_constants.stop_hook_hold_constants import BLOCK_EXIT_CODE
from hooks_constants.user_step_wording_constants import CODE_SPAN_STAND_IN


def is_exempt_stop(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True for a subagent, a Cursor stop, or a headless run."""
    if all_hook_input_fields.get(SUBAGENT_ID_KEY) or all_hook_input_fields.get(
        CURSOR_CONVERSATION_ID_KEY
    ):
        return True
    return os.environ.get(SESSION_ATTENDED_ENVIRONMENT_VARIABLE) == HEADLESS_SESSION_ATTENDED_TEXT


def has_background_work(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True when the payload's ``background_tasks`` is a non-empty list, object, or string."""
    return background_job_count(all_hook_input_fields) > 0


def background_job_count(all_hook_input_fields: dict[str, object]) -> int:
    """Return how many pieces of background work the payload's ``background_tasks`` names.

    ::

        [{"id": "a"}, {"id": "b"}]   -> 2
        {"a": {...}}                 -> 1
        "ledger"                     -> 1
        missing, empty, or a number  -> 0
    """
    all_background_tasks = all_hook_input_fields.get(BACKGROUND_TASKS_KEY)
    if isinstance(all_background_tasks, (list, dict)):
        return len(all_background_tasks)
    return int(isinstance(all_background_tasks, str) and bool(all_background_tasks))


def _record_text(all_record_fields: dict[str, object]) -> str:
    message_body = all_record_fields.get(MESSAGE_KEY)
    content_value = message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
    if isinstance(content_value, str):
        return content_value
    return WORD_SEPARATOR.join(block_texts(all_record_fields))


def _is_own_hold(all_record_fields: dict[str, object]) -> bool:
    if all_record_fields.get(RECORD_TYPE_KEY) != USER_RECORD_TYPE:
        return False
    feedback_text = _record_text(all_record_fields).lstrip()
    if not feedback_text.startswith(STOP_HOOK_FEEDBACK_PREFIX):
        return False
    feedback_opening = feedback_text[:FEEDBACK_OPENING_LENGTH]
    return any(each_lead in feedback_opening for each_lead in ALL_REASON_LEADS)


def prior_hold_count(all_counted_records: list[dict[str, object]]) -> int:
    """Return how many times this gate already held a stop among the records.

    A hold is a ``user`` record whose text starts with "Stop hook feedback" and
    carries the first sentence of either of this gate's reasons within its
    first 200 characters. A record that quotes the sentence further in, such
    as a worker's report, is no hold.
    """
    return sum(_is_own_hold(each_record) for each_record in all_counted_records)


def _quoted_line(open_line: str) -> str:
    shown_line = open_line.replace(CODE_SPAN_STAND_IN, CODE_SPAN_SHOWN_TEXT)
    if len(shown_line) > MAXIMUM_QUOTED_LINE_LENGTH:
        kept_length = MAXIMUM_QUOTED_LINE_LENGTH - len(CLIPPED_LINE_END)
        shown_line = shown_line[:kept_length] + CLIPPED_LINE_END
    return QUOTED_LINE_TEMPLATE.format(line=shown_line)


def closing_round_reason(all_open_item_lines: list[str]) -> str:
    """Return the hold reason: the fixed first sentence, the quoted lines, and the instruction.

    The last 8 lines at most are quoted, each cut to 160 characters, because
    the newest lines are the ones most likely to still stand. A count of the
    earlier lines follows them when there are more.
    """
    all_quoted_lines = [
        _quoted_line(each_line) for each_line in all_open_item_lines[-MAXIMUM_QUOTED_LINE_COUNT:]
    ]
    remaining_count = len(all_open_item_lines) - len(all_quoted_lines)
    all_remaining_notes = (
        [REMAINING_LINES_TEMPLATE.format(remaining_count=remaining_count)]
        if remaining_count
        else []
    )
    return REASON_PART_SEPARATOR.join(
        [
            CLOSING_ROUND_REASON_LEAD,
            OPEN_ITEM_LINES_LABEL,
            *all_quoted_lines,
            *all_remaining_notes,
            CLOSING_ROUND_INSTRUCTION,
        ]
    )


class FooterSeen(NamedTuple):
    """One footer the user saw, and where it sits in the session.

    Attributes:
        lines: The footer's items.
        count_start: The transcript line where footer counting starts: after the last
            typed prompt, or after the last answered question when that comes later.
        occurrence: How many footer replies since that line end with it, this one included.
    """

    lines: tuple[str, ...]
    count_start: int
    occurrence: int


class CoveredSession(NamedTuple):
    """The parts of a session the gate reads.

    Attributes:
        all_payload_texts: The closing reply texts the payload adds.
        all_stretch_records: The top-level records after the last question call that reached the user.
        all_counted_records: The stretch records after the last typed prompt, where holds count.
        newest_footer: The newest footer among the counted records, or None.
        count_start: The transcript line where footer counting starts.
        written_reply: The reply the transcript ends with, or None when a prompt or work comes after it.
    """

    all_payload_texts: list[str]
    all_stretch_records: list[dict[str, object]]
    all_counted_records: list[dict[str, object]]
    newest_footer: FooterSeen | None
    count_start: int
    written_reply: str | None


def _assistant_messages(all_records: list[dict[str, object]]) -> list[tuple[int, str, bool]]:
    all_parts_by_message: dict[object, list[str]] = {}
    last_text_positions: dict[object, int] = {}
    all_tool_message_keys: set[object] = set()
    for each_position, each_record in enumerate(all_records):
        message_id = _message_id(each_record)
        message_key = each_position if message_id is None else message_id
        if _has_tool_call(each_record):
            all_tool_message_keys.add(message_key)
        all_record_texts = block_texts(each_record) if is_assistant_record(each_record) else []
        if not all_record_texts:
            continue
        all_parts_by_message.setdefault(message_key, []).extend(all_record_texts)
        last_text_positions[message_key] = each_position
    return sorted(
        (
            last_text_positions[each_key],
            REPLY_PART_JOINER.join(all_parts),
            each_key in all_tool_message_keys,
        )
        for each_key, all_parts in all_parts_by_message.items()
    )


def _footer_messages(all_records: list[dict[str, object]]) -> list[tuple[int, str]]:
    return [
        (each_position, each_text)
        for each_position, each_text, has_tool_call in _assistant_messages(all_records)
        if not has_tool_call and split_footer(each_text).footer_items is not None
    ]


def _footer_positions(all_records: list[dict[str, object]]) -> list[int]:
    return [each_position for each_position, _ in _footer_messages(all_records)]


def _has_tool_call(all_record_fields: dict[str, object]) -> bool:
    return any(
        each_block.get(RECORD_TYPE_KEY) == TOOL_USE_BLOCK_TYPE for each_block in _content_blocks(all_record_fields)
    )


def _job_identity(job_entry: object) -> str:
    all_named_ids = (
        [job_entry.get(each_key) for each_key in ALL_BACKGROUND_JOB_ID_KEYS] if isinstance(job_entry, dict) else []
    )
    return next(
        (each_id for each_id in all_named_ids if isinstance(each_id, str)),
        json.dumps(job_entry, sort_keys=True, default=str),
    )


def _job_identities(all_background_tasks: object) -> list[str]:
    if isinstance(all_background_tasks, dict):
        return [str(each_name) for each_name in all_background_tasks]
    if isinstance(all_background_tasks, list):
        return [_job_identity(each_entry) for each_entry in all_background_tasks]
    if isinstance(all_background_tasks, str) and all_background_tasks:
        return [all_background_tasks]
    return []


class FooterSnapshot(NamedTuple):
    """What the gate keeps about the newest footer that went out while background work ran.

    Attributes:
        footer_key: Names the footer's lines and where it sits in the session.
        state_key: Names the tasks in progress and the background jobs at that moment.
        job_count: How many background jobs ran then.
        is_pending: Whether the footer came from the payload before the
            transcript held it, so a later stop that carries it again
            writes its own jobs over this snapshot.
        record_count: How many counted records the transcript held when a
            pending footer was kept, so the reply written next is its own.
        reply_key: Names the whole reply a pending footer came in, so only
            that reply, written next, keeps its jobs.
    """

    footer_key: str
    state_key: str
    job_count: int
    is_pending: bool = False
    record_count: int = 0
    reply_key: str = NO_REPLY_KEY


def _short_digest(all_parts: list[object]) -> str:
    digest = hashlib.sha256(json.dumps(all_parts).encode()).hexdigest()
    return FOOTER_JOBS_KEY_TEMPLATE.format(digest=digest[:FOOTER_JOBS_DIGEST_LENGTH])


def footer_key(footer: FooterSeen) -> str:
    """Return a short key that names one footer occurrence.

    ::

        footer F, counting from line 4, first footer      -> "footer-jobs-<digest>"
        the same words as the second footer since then    -> another key
        the same words after another prompt or answer     -> another key
    """
    return _short_digest([list(footer.lines), footer.count_start, footer.occurrence])


def footer_snapshot(
    all_hook_input_fields: dict[str, object], footer: FooterSeen, all_tasks: SessionTasks
) -> FooterSnapshot:
    """Return the snapshot of one footer with the tasks in progress and the payload's background jobs.

    ::

        footer F, tasks #28, jobs [{"id": "b"}, {"id": "a"}]  -> (key of F, key of #28 and a, b, 2)
        jobs ["ab", "c"] and ["a", "bc"]                       -> two different state keys
        tasks #28 and #29, then #28 alone                      -> two different state keys
        task #28, then #28 with a new subject                  -> two different state keys
        task #28, then #28 with a new description              -> two different state keys
        jobs "ledger" and {"ledger": {}}                       -> the same state key

    Args:
        all_hook_input_fields: The Stop hook payload.
        footer: The footer the jobs went out with.
        all_tasks: The session's tasks.

    Returns:
        The snapshot for that footer, task set, and job set.
    """
    all_identities = sorted(_job_identities(all_hook_input_fields.get(BACKGROUND_TASKS_KEY)))
    all_task_entries = sorted(
        [each_task.item_id, each_task.subject, each_task.description] for each_task in all_tasks.in_progress
    )
    return FooterSnapshot(footer_key(footer), _short_digest([all_task_entries, all_identities]), len(all_identities))


def _snapshot_path(all_hook_input_fields: dict[str, object]) -> Path | None:
    session_id = all_hook_input_fields.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return None
    file_name = FOOTER_JOBS_FILE_TEMPLATE.format(marker=FOOTER_JOBS_MARKER_NAME, session=session_file_id(session_id))
    return Path(tempfile.gettempdir()) / file_name


def _snapshot_line(snapshot: FooterSnapshot) -> str:
    pending_mark = FOOTER_SNAPSHOT_PENDING_MARK if snapshot.is_pending else FOOTER_SNAPSHOT_SENT_MARK
    return FOOTER_SNAPSHOT_SEPARATOR.join(
        [
            snapshot.footer_key,
            snapshot.state_key,
            str(snapshot.job_count),
            pending_mark,
            str(snapshot.record_count),
            snapshot.reply_key,
        ]
    )


def record_footer_jobs(
    all_hook_input_fields: dict[str, object],
    footer: FooterSeen,
    all_tasks: SessionTasks,
    all_kept_snapshots: tuple[FooterSnapshot, ...] | None = None,
    is_pending: bool = False,
    record_count: int = 0,
    closing_reply: str = "",
) -> None:
    """Keep this footer, its tasks, and its jobs as the session's snapshot of that footer.

    ::

        footer F with job a, then F with jobs a and b   -> the snapshot of F is F with a and b
        footer F with no jobs                           -> the snapshot of F is F with no jobs
        footer F, then footer G                         -> both kept, G first
        payload with no session id                      -> nothing kept
        the snapshot name is a symlink                  -> the new file takes the name, the target untouched

    The snapshot sits in the shared temp folder, so it is written to a new
    file created with mode 0600 that no other file can stand behind, and
    then moved onto the snapshot name. A move takes the name, link or not,
    and never follows a link, on Windows too. The file keeps the newest
    three footers, so a footer read from the payload before the transcript
    holds it leaves the snapshot of the footer the transcript shows. A
    caller that already read the kept snapshots passes them, so the file
    is read once. A footer read only from the payload is kept as pending,
    with how many counted records the transcript held then and a digest
    of the whole reply it came in.
    """
    snapshot_path = _snapshot_path(all_hook_input_fields)
    if snapshot_path is None:
        return
    snapshot = footer_snapshot(all_hook_input_fields, footer, all_tasks)._replace(
        is_pending=is_pending,
        record_count=record_count if is_pending else 0,
        reply_key=reply_key(closing_reply) if is_pending else NO_REPLY_KEY,
    )
    all_other_snapshots = [
        each_snapshot
        for each_snapshot in (
            kept_footer_snapshots(all_hook_input_fields) if all_kept_snapshots is None else all_kept_snapshots
        )
        if each_snapshot.footer_key != snapshot.footer_key
    ]
    all_kept_snapshots = [snapshot, *all_other_snapshots][:FOOTER_SNAPSHOT_KEPT_COUNT]
    snapshot_text = FOOTER_SNAPSHOT_LINE_SEPARATOR.join(_snapshot_line(each) for each in all_kept_snapshots)
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=snapshot_path.name, suffix=FOOTER_JOBS_TEMP_SUFFIX, dir=snapshot_path.parent
        )
    except OSError:
        return
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            file_descriptor, "w", encoding=FOOTER_JOBS_TEXT_ENCODING, newline=FOOTER_SNAPSHOT_LINE_SEPARATOR
        ) as snapshot_file:
            snapshot_file.write(snapshot_text)
        os.chmod(temporary_path, FOOTER_JOBS_FILE_MODE)
        os.replace(temporary_path, snapshot_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)


def kept_footer_snapshot(
    all_hook_input_fields: dict[str, object], footer: FooterSeen | None
) -> FooterSnapshot | None:
    """Return the session's kept snapshot of this footer, or None when none names it.

    ::

        footer F, a snapshot of F and one of G kept      -> the snapshot of F
        footer F, only a snapshot of G kept              -> None
        no footer                                         -> None
    """
    if footer is None:
        return None
    wanted_key = footer_key(footer)
    return next(
        (
            each_snapshot
            for each_snapshot in kept_footer_snapshots(all_hook_input_fields)
            if each_snapshot.footer_key == wanted_key
        ),
        None,
    )


def kept_footer_snapshots(all_hook_input_fields: dict[str, object]) -> tuple[FooterSnapshot, ...]:
    """Return the session's kept footer snapshots, newest first, or none when none can be read.

    ::

        snapshots written by ``record_footer_jobs``      -> those snapshots
        the same lines ended by \r\n                       -> those snapshots
        no snapshot, a symlink, or a damaged file       -> ()

    The read checks that the name holds a regular file, not a link, and that
    the file it opened is that same file, so a link is refused on Windows
    too, where no open flag refuses one.
    """
    snapshot_path = _snapshot_path(all_hook_input_fields)
    if snapshot_path is None:
        return ()
    try:
        name_status = os.lstat(snapshot_path)
        if not stat.S_ISREG(name_status.st_mode):
            return ()
        file_descriptor = os.open(snapshot_path, os.O_RDONLY | NO_FOLLOW_FLAG)
    except OSError:
        return ()
    with os.fdopen(file_descriptor, "rb") as snapshot_file:
        if not os.path.samestat(name_status, os.fstat(snapshot_file.fileno())):
            return ()
        kept_text = snapshot_file.read(FOOTER_JOBS_READ_LIMIT).decode(FOOTER_JOBS_TEXT_ENCODING, errors="replace")
    all_snapshots = [_parsed_snapshot(each_line) for each_line in kept_text.splitlines()]
    if None in all_snapshots:
        return ()
    return tuple(each_snapshot for each_snapshot in all_snapshots if each_snapshot is not None)


def _parsed_snapshot(snapshot_line: str) -> FooterSnapshot | None:
    all_parts = snapshot_line.split(FOOTER_SNAPSHOT_SEPARATOR)
    if len(all_parts) != FOOTER_SNAPSHOT_PART_COUNT or not all_parts[2].isdigit() or not all_parts[4].isdigit():
        return None
    if all_parts[3] not in (FOOTER_SNAPSHOT_PENDING_MARK, FOOTER_SNAPSHOT_SENT_MARK):
        return None
    return FooterSnapshot(
        all_parts[0],
        all_parts[1],
        int(all_parts[2]),
        all_parts[3] == FOOTER_SNAPSHOT_PENDING_MARK,
        int(all_parts[4]),
        all_parts[5],
    )


def were_jobs_shown(
    kept_snapshot: FooterSnapshot | None,
    all_hook_input_fields: dict[str, object],
    footer: FooterSeen | None,
    all_tasks: SessionTasks,
) -> bool:
    """Return True when the kept snapshot is this footer with exactly these tasks and jobs.

    ::

        footer F sent while job a ran, F newest, job a runs now        -> True
        footer F sent while job a ran, job b took its place            -> False
        F with job a, then F again with jobs a and b, then job a alone -> False
        F with tasks #28 and #29 and job a, #29 finished               -> False
        no footer, or no snapshot kept for this session                -> False

    Args:
        kept_snapshot: The session's kept snapshot of the footer, from ``kept_footer_snapshot``.
        all_hook_input_fields: The Stop hook payload.
        footer: The newest footer the user saw, or None.
        all_tasks: The session's tasks.

    Returns:
        Whether the snapshot names that footer with exactly these tasks and jobs.
    """
    if footer is None or kept_snapshot is None:
        return False
    return kept_snapshot._replace(is_pending=False, record_count=0, reply_key=NO_REPLY_KEY) == footer_snapshot(
        all_hook_input_fields, footer, all_tasks
    )


def is_footer_recorded(kept_snapshot: FooterSnapshot | None, footer: FooterSeen | None) -> bool:
    """Return True when the kept snapshot names this footer, whatever tasks and jobs it holds.

    ::

        footer F sent while job a ran, F newest             -> True
        footer F sent with no background work               -> True
        a snapshot of another footer                        -> False
        no footer, or no snapshot kept for this session     -> False
    """
    if footer is None or kept_snapshot is None:
        return False
    return kept_snapshot.footer_key == footer_key(footer)


def _covered_session(
    all_hook_input_fields: dict[str, object], deadline_at: float
) -> CoveredSession | None:
    all_lines = transcript_lines(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY), deadline_at)
    prompt_position = last_typed_prompt_position(all_lines, deadline_at)
    if prompt_position is None:
        return None
    start_position = stretch_start(all_lines, deadline_at)
    count_start = max(start_position, prompt_position + 1)
    all_counted_records = top_level_records(all_lines[count_start:], deadline_at)
    all_stretch_records = [
        *top_level_records(all_lines[start_position:count_start], deadline_at),
        *all_counted_records,
    ]
    written_reply = last_written_reply(all_lines, deadline_at)
    return CoveredSession(
        payload_closing_texts(all_hook_input_fields, written_reply),
        all_stretch_records,
        all_counted_records,
        _newest_footer(all_counted_records, count_start),
        count_start,
        written_reply,
    )


def _newest_footer(all_counted_records: list[dict[str, object]], count_start: int) -> FooterSeen | None:
    all_footer_messages = _footer_messages(all_counted_records)
    if not all_footer_messages:
        return None
    return FooterSeen(
        split_footer(all_footer_messages[-1][1]).footer_items or (),
        count_start,
        len(all_footer_messages),
    )


def _has_work_since_footer(all_stretch_records: list[dict[str, object]]) -> bool:
    all_footer_positions = _footer_positions(all_stretch_records)
    start_position = all_footer_positions[-1] + 1 if all_footer_positions else 0
    return has_work_call(all_stretch_records[start_position:])


def _closing_reply_texts(
    all_stretch_records: list[dict[str, object]], all_payload_texts: list[str]
) -> list[str]:
    all_work_positions = [
        each_position
        for each_position, each_record in enumerate(all_stretch_records)
        if has_work_call([each_record])
    ]
    first_closing_position = all_work_positions[-1] + 1 if all_work_positions else 0
    all_closing_messages = _assistant_messages(all_stretch_records[first_closing_position:])
    return [*(each_text for _, each_text, _ in all_closing_messages), *all_payload_texts]


def _missing_footer_lead(
    all_tasks: SessionTasks, is_declared: bool, did_work: bool, is_recorded: bool
) -> str | None:
    if is_declared and all_tasks.in_progress:
        return IN_PROGRESS_TASKS_REASON_LEAD
    if did_work:
        return FOOTER_MISSING_REASON_LEAD
    if is_recorded:
        return FOOTER_CHANGED_REASON_LEAD
    return None


def is_footer_still_current(
    all_last_footer_lines: tuple[str, ...] | None,
    all_tasks: SessionTasks,
    background_count: int,
    were_jobs_in_footer: bool = False,
    is_recorded: bool = False,
) -> bool:
    """Return True when the newest footer the user saw still shows the work in progress.

    ::

        footer names #28 and #29, both in progress                -> True
        footer names #28 and #29, #29 finished                    -> False, one line too many
        footer names #28, #29 started since                       -> False, #29 left out
        footer kept with #28, #30 took its place since            -> False, the tasks changed
        footer names #28 and the jobs it went out with, still running -> True
        footer names only #28, its line says the tests still run     -> True, the jobs it went out with still run
        footer names #28, a job started in the background since    -> False, the jobs changed
        one job took another's place since                         -> False, the jobs changed
        the footer went out with a job that has ended since        -> False, the job ended
        no footer since the typed prompt or answered card         -> False

    The footer has one line per piece of work. With no background work, a
    footer with more lines than tasks in progress shows work that is done,
    and a footer the gate kept a snapshot of must have gone out with exactly
    these tasks in progress and no jobs. With background work, this footer
    must have gone out while exactly these jobs ran. The footer may tell
    the user about the jobs in a line of their own or in the line of the
    task they serve, as the first stop accepts it. A job that starts, ends,
    or takes another's place makes it owed, while a notice that a job is
    still going does not.

    Args:
        all_last_footer_lines: The lines of the newest footer sent, or None.
        all_tasks: The session's tasks.
        background_count: How many background jobs the payload names.
        were_jobs_in_footer: Whether this footer went out while exactly these jobs ran.
        is_recorded: Whether the kept snapshot names this footer.

    Returns:
        Whether the footer can stand for the reply.
    """
    if all_last_footer_lines is None:
        return False
    if left_out_tasks(all_last_footer_lines, all_tasks.in_progress, all_tasks.still_open):
        return False
    if background_count:
        return were_jobs_in_footer
    if len(all_last_footer_lines) > len(all_tasks.in_progress):
        return False
    return were_jobs_in_footer or not is_recorded


def footer_hold_reason(
    all_hook_input_fields: dict[str, object],
    closing_reply: str,
    did_work: bool,
    deadline_at: float,
    newest_footer: FooterSeen | None = None,
    all_known_tasks: SessionTasks | None = None,
    all_counted_records: list[dict[str, object]] | None = None,
) -> str | None:
    """Return the footer hold reason for the closing reply, or None when the reply may end.

    ::

        nothing in progress, no background work           -> None, no closing line owed
        "Open items: none."  task #28 in_progress          -> the declaration reason
        work, no footer, task #28 or background work       -> the missing-footer reason
        a footer that leaves out in-progress task #29      -> the gap reason
        a footer that names every in-progress task         -> None
        no work, no footer, no footer since the typed
            prompt or answered card                        -> None, a chat-only turn
        no work, no footer, the tasks or jobs changed
            since the newest footer                        -> the changed-work reason
        no work, no footer, nothing changed since the
            newest footer                                  -> None, a waiting notice
        work, no footer, an earlier footer since the typed
            prompt or answered card still shows the work   -> None, the footer is not sent again
        a pending snapshot of another reply's footer       -> the snapshot is not read

    Args:
        all_hook_input_fields: The Stop payload, read for ``background_tasks``
            and the task list.
        closing_reply: The newest text after the last work call.
        did_work: Whether the stretch holds work after the last reply that
            ended with the footer.
        deadline_at: The monotonic time the declaration scan stops at.
        newest_footer: The newest footer sent since the later of the last
            typed prompt and the last question call that reached the user, or
            None when no reply since then ended with one.
        all_known_tasks: The session's tasks when the caller already read
            them, or None to read them here.
        all_counted_records: The counted records, so a pending snapshot
            counts only when the reply written next after its stop is the
            reply it was kept for.

    Returns:
        The reason, or None.
    """
    footer_items = split_footer(closing_reply).footer_items
    is_declared = footer_items is None and declares_no_open_items(closing_reply, deadline_at)
    if footer_items is None and not is_declared and not did_work and newest_footer is None:
        return None
    all_tasks = all_known_tasks if all_known_tasks is not None else session_tasks(all_hook_input_fields)
    if not all_tasks.in_progress and not has_background_work(all_hook_input_fields):
        return None
    if footer_items is None:
        kept_snapshot = kept_footer_snapshot(all_hook_input_fields, newest_footer)
        if kept_snapshot is not None and kept_snapshot.is_pending and not _is_written_by_its_stop(
            kept_snapshot, all_counted_records or [], _newest_footer_reply(all_counted_records or []) or ""
        ):
            kept_snapshot = None
        is_recorded = is_footer_recorded(kept_snapshot, newest_footer)
        if not is_declared and not did_work and not is_recorded:
            return None
        if not is_declared and is_footer_still_current(
            None if newest_footer is None else newest_footer.lines,
            all_tasks,
            background_job_count(all_hook_input_fields),
            were_jobs_shown(kept_snapshot, all_hook_input_fields, newest_footer, all_tasks),
            is_recorded,
        ):
            return None
        reason_lead = _missing_footer_lead(all_tasks, is_declared, did_work, is_recorded)
        if reason_lead is None:
            return None
        return footer_reason(reason_lead, all_tasks.in_progress, (), all_tasks.still_open)
    all_left_out_items = left_out_tasks(footer_items, all_tasks.in_progress, all_tasks.still_open)
    if not all_left_out_items:
        return None
    return footer_reason(
        FOOTER_GAP_REASON_LEAD, all_tasks.in_progress, all_left_out_items, all_tasks.still_open
    )


def _scanned_text(reply_text: str) -> str:
    split_reply = split_footer(reply_text)
    if split_reply.footer_items is None:
        return reply_text
    all_scanned_items = [
        FOOTER_STATUS_MARKER_PATTERN.sub(FOOTER_STATUS_STAND_IN, each_item)
        for each_item in split_reply.footer_items
    ]
    return SCANNED_PARAGRAPH_SEPARATOR.join([split_reply.body, *all_scanned_items])


def _new_footer(
    all_hook_input_fields: dict[str, object], closing_reply: str, covered_session: CoveredSession
) -> FooterSeen | None:
    payload_reply = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    all_footer_items = split_footer(closing_reply).footer_items
    if not isinstance(payload_reply, str) or not payload_reply.strip():
        return _closing_transcript_footer(all_footer_items, covered_session)
    if not is_same_reply(payload_reply, closing_reply) or all_footer_items is None:
        return None
    is_unwritten = any(
        is_same_reply(each_text, closing_reply) for each_text in covered_session.all_payload_texts
    )
    if not is_unwritten:
        return _closing_transcript_footer(all_footer_items, covered_session)
    footer_count = len(_footer_positions(covered_session.all_counted_records))
    return FooterSeen(tuple(all_footer_items), covered_session.count_start, footer_count + 1)


def _closing_transcript_footer(
    all_footer_items: tuple[str, ...] | None, covered_session: CoveredSession
) -> FooterSeen | None:
    newest_footer = covered_session.newest_footer
    written_reply = covered_session.written_reply
    if newest_footer is None or written_reply is None or all_footer_items != newest_footer.lines:
        return None
    if split_footer(_newest_footer_reply(covered_session.all_counted_records) or "").footer_items != newest_footer.lines:
        return None
    return newest_footer if _is_newest_footer_last_text(covered_session.all_counted_records) else None


def _is_newest_footer_last_text(all_counted_records: list[dict[str, object]]) -> bool:
    all_text_positions = [
        each_position
        for each_position, each_record in enumerate(all_counted_records)
        if is_assistant_record(each_record) and block_texts(each_record)
    ]
    return all_text_positions[-1] == _footer_positions(all_counted_records)[-1]


def reply_key(closing_reply: str) -> str:
    """Return a short digest that names a whole closing reply, so two replies that share a footer differ.

    ::

        "Done.\\n\\nIn progress:\\n- I am shipping 8590."  -> one key
        "Merged.\\n\\nIn progress:\\n- I am shipping 8590." -> another key
        the first reply with white space around it        -> the first key
        the first reply with one more blank line           -> the first key
        the first reply with its item indented             -> another key

    The digest reads the lines ``reply_lines`` keeps, so a reply written as
    two records of one message matches the whole reply the payload carried,
    while a reply laid out another way does not.
    """
    return _short_digest(reply_lines(closing_reply))


def _is_written_by_its_stop(
    snapshot: FooterSnapshot, all_counted_records: list[dict[str, object]], closing_reply: str
) -> bool:
    if snapshot.reply_key != reply_key(closing_reply):
        return False
    all_later_positions = [
        each_position
        for each_position, each_record in enumerate(all_counted_records)
        if each_position >= snapshot.record_count and is_assistant_record(each_record)
    ]
    all_footer_positions = _footer_positions(all_counted_records)
    if not all_later_positions or not all_footer_positions:
        return False
    first_record = all_counted_records[all_later_positions[0]]
    footer_record = all_counted_records[all_footer_positions[-1]]
    if all_later_positions[0] == all_footer_positions[-1]:
        return True
    footer_message_id = _message_id(footer_record)
    return footer_message_id is not None and _message_id(first_record) == footer_message_id


def _is_unrecorded(
    all_kept_snapshots: tuple[FooterSnapshot, ...],
    new_footer: FooterSeen,
    is_pending: bool,
    all_counted_records: list[dict[str, object]],
    closing_reply: str,
) -> bool:
    """Return True when no kept snapshot of this footer should stand.

    ::

        no snapshot of the footer                                -> True
        a sent snapshot of it                                    -> False
        a pending snapshot, the footer read from the payload again -> True
        a pending snapshot, the reply written right after its stop -> False, its jobs stand
        a pending snapshot, other records written before the reply -> True, the snapshot was stale
        a pending snapshot, another reply with the same footer next -> True, the snapshot was stale
    """
    new_footer_key = footer_key(new_footer)
    return all(
        each_snapshot.footer_key != new_footer_key
        or (each_snapshot.is_pending and (is_pending or not _is_written_by_its_stop(each_snapshot, all_counted_records, closing_reply)))
        for each_snapshot in all_kept_snapshots
    )


def _hold_reason(all_hook_input_fields: dict[str, object], deadline_at: float) -> str | None:
    covered_session = _covered_session(all_hook_input_fields, deadline_at)
    if covered_session is None:
        return None
    all_payload_texts, all_stretch_records, all_counted_records, newest_footer, _, written_reply = covered_session
    if prior_hold_count(all_counted_records) >= MAXIMUM_HOLD_COUNT:
        return None
    all_closing_texts = (
        _closing_reply_texts(all_stretch_records, all_payload_texts)
        if all_payload_texts or written_reply is not None
        else []
    )
    closing_reply = all_closing_texts[-1] if all_closing_texts else ""
    new_footer = _new_footer(all_hook_input_fields, closing_reply, covered_session)
    all_known_tasks = None
    all_kept_snapshots = () if new_footer is None else kept_footer_snapshots(all_hook_input_fields)
    is_pending = new_footer != newest_footer
    if new_footer is not None and _is_unrecorded(
        all_kept_snapshots,
        new_footer,
        is_pending,
        all_counted_records,
        closing_reply if is_pending else _newest_footer_reply(all_counted_records) or closing_reply,
    ):
        all_known_tasks = session_tasks(all_hook_input_fields)
        record_footer_jobs(
            all_hook_input_fields,
            new_footer,
            all_known_tasks,
            all_kept_snapshots,
            is_pending,
            len(all_counted_records),
            closing_reply,
        )
    all_texts = [
        _scanned_text(each_text)
        for each_text in [*(each_message_text for _, each_message_text, _ in _assistant_messages(all_stretch_records)), *all_payload_texts]
    ]
    if not has_background_work(all_hook_input_fields):
        all_open_item_lines = marked_open_lines(all_texts, deadline_at)
        if all_open_item_lines:
            return closing_round_reason(all_open_item_lines)
    return footer_hold_reason(
        all_hook_input_fields,
        closing_reply,
        _has_work_since_footer(all_stretch_records),
        deadline_at,
        newest_footer,
        all_known_tasks,
        all_counted_records,
    )


def _newest_footer_reply(all_counted_records: list[dict[str, object]]) -> str | None:
    all_footer_messages = _footer_messages(all_counted_records)
    if not all_footer_messages:
        return None
    return all_footer_messages[-1][1] or None


def _capped_hook_input() -> dict[str, object] | None:
    payload_bytes = sys.stdin.buffer.read(MAXIMUM_PAYLOAD_BYTES + 1)
    if len(payload_bytes) > MAXIMUM_PAYLOAD_BYTES:
        return None
    payload_text = payload_bytes.decode(errors="replace").strip().removeprefix(UTF8_BYTE_ORDER_MARK)
    try:
        parsed_payload = json.loads(payload_text)
    except ValueError:
        return None
    return parsed_payload if isinstance(parsed_payload, dict) else None


def _stop_decision(deadline_at: float) -> int:
    all_hook_input_fields = _capped_hook_input()
    if (
        all_hook_input_fields is None
        or is_exempt_stop(all_hook_input_fields)
        or is_bypass_on(all_hook_input_fields)
    ):
        return ALLOW_EXIT_CODE
    block_reason = _hold_reason(all_hook_input_fields, deadline_at)
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, HOOK_EVENT_NAME, block_reason)
    return hold_stop(all_hook_input_fields, block_reason)


def _allow_now(output_lock: threading.Lock) -> None:
    if output_lock.acquire(blocking=False):
        os._exit(ALLOW_EXIT_CODE)


def main() -> int:
    """Decide the stop in this process and return its exit code."""
    deadline_at = time.monotonic() + STOP_DEADLINE_SECONDS
    try:
        return _stop_decision(deadline_at)
    except Exception:
        return ALLOW_EXIT_CODE


def _decision_run(payload_bytes: bytes, deadline_at: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), DECISION_PROCESS_FLAG],
        input=payload_bytes,
        capture_output=True,
        timeout=max(deadline_at - time.monotonic(), 0.0),
        check=False,
    )


def _relayed_exit_code(completed_decision: subprocess.CompletedProcess[bytes]) -> int:
    output_watchdog = threading.Timer(OUTPUT_WATCHDOG_SECONDS, os._exit, args=(ALLOW_EXIT_CODE,))
    output_watchdog.daemon = True
    output_watchdog.start()
    all_outputs = (
        (sys.stderr, completed_decision.stderr),
        (sys.stdout, completed_decision.stdout),
    )
    try:
        for each_stream, each_output in all_outputs:
            each_stream.buffer.write(each_output)
            each_stream.buffer.flush()
    except (OSError, ValueError):
        return ALLOW_EXIT_CODE
    finally:
        output_watchdog.cancel()
    return completed_decision.returncode


def supervised_main() -> int:
    """Run ``main`` in a child process and allow the stop when it outlasts 8 seconds.

    One C-level step, such as a JSON parse, can hold the interpreter for seconds,
    and no thread of the same process runs then. The child is killed at the
    deadline, and a watchdog thread here ends a stdin read that never finishes
    at 8.5 seconds. A child that exits with a code other than 0 or 2 allows
    the stop with no output, and so do a closed standard stream and output
    that cannot be written. Both streams are written and flushed here, stderr
    first, so stdout holds the hold only once the reason reached stderr, and a
    write that has not finished 1 second after it starts, such as one to a
    full pipe nobody reads, ends the process with 0.
    """
    if sys.stdin is None or sys.stdout is None or sys.stderr is None:
        return ALLOW_EXIT_CODE
    deadline_at = time.monotonic() + STOP_DEADLINE_SECONDS + WATCHDOG_GRACE_SECONDS
    output_lock = threading.Lock()
    watchdog = threading.Timer(STDIN_WATCHDOG_SECONDS, _allow_now, args=(output_lock,))
    watchdog.daemon = True
    watchdog.start()
    try:
        payload_bytes = sys.stdin.buffer.read(MAXIMUM_PAYLOAD_BYTES + 1)
        if len(payload_bytes) > MAXIMUM_PAYLOAD_BYTES:
            return ALLOW_EXIT_CODE
        completed_decision = _decision_run(payload_bytes, deadline_at)
    except (OSError, subprocess.SubprocessError):
        return ALLOW_EXIT_CODE
    finally:
        watchdog.cancel()
    if completed_decision.returncode not in (ALLOW_EXIT_CODE, BLOCK_EXIT_CODE):
        return ALLOW_EXIT_CODE
    if not output_lock.acquire(blocking=False):
        return ALLOW_EXIT_CODE
    return _relayed_exit_code(completed_decision)


if __name__ == "__main__":
    if DECISION_PROCESS_FLAG in sys.argv[1:]:
        sys.exit(main())
    os._exit(supervised_main())
