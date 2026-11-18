#!/usr/bin/env python3
"""Stop hook that ends a working reply with an In progress footer or a question card round.

The gate holds the stop for these shapes, and only in a session it covers::

    hold:  "I deferred the backoff setting."        no question card after it
    hold:  "Nothing is deferred."                   a marker line; negation does not cancel it
    allow: a marker line, then an answered AskUserQuestion call
    allow: an Edit call, then "Done."               nothing in progress, no closing line owed
    hold:  an Edit call, then "Done."               task #28 in_progress: the footer is owed
    allow: an Edit call, then the footer naming task #28
    hold:  the footer that names #28 and leaves out in-progress task #29
    hold:  "Open items: none." beside task #28 in_progress

The stretch is every top-level record after the last question call that
reached the user, then the payload's closing reply. The closing reply is the
newest text after the last work call. Each reply's In progress footer, as
``closing_question_round_footer.split_footer`` reads it, is cut off first, so
a marker word inside a footer counts for nothing; a footer item that ends with
a question mark stays in the scan. A marker line is a prose
line ``closing_question_round_open_items`` finds in the rest: a marker word or
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
- Work with work in progress and no footer holds the stop.
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

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

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
    assistant_texts,
    block_texts,
    closing_reply_texts,
    has_work_call,
    last_typed_prompt_position,
    stretch_start,
    top_level_records,
)
from open_tasks_transcript_records import is_assistant_record

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
    REMAINING_LINES_TEMPLATE,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    STDIN_WATCHDOG_SECONDS,
    STOP_DEADLINE_SECONDS,
    SUBAGENT_ID_KEY,
    WATCHDOG_GRACE_SECONDS,
)
from hooks_constants.final_reply_gate_constants import QUESTION_MARK, TRAILING_MARKUP_CHARACTERS
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.setup_project_paths_constants import UTF8_BYTE_ORDER_MARK
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    CONTENT_KEY,
    CURSOR_CONVERSATION_ID_KEY,
    HOOK_EVENT_NAME,
    MESSAGE_KEY,
    RECORD_TYPE_KEY,
    STOP_HOOK_FEEDBACK_PREFIX,
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
    all_background_tasks = all_hook_input_fields.get(BACKGROUND_TASKS_KEY)
    return isinstance(all_background_tasks, (list, dict, str)) and bool(all_background_tasks)


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


def _covered_texts_and_records(
    all_hook_input_fields: dict[str, object], deadline_at: float
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]] | None:
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
    all_payload_texts = closing_reply_texts(all_hook_input_fields, all_lines, deadline_at)
    return all_payload_texts, all_stretch_records, all_counted_records


def _has_work_since_footer(all_stretch_records: list[dict[str, object]]) -> bool:
    start_position = 0
    for each_position in range(len(all_stretch_records) - 1, -1, -1):
        each_record = all_stretch_records[each_position]
        all_record_texts = block_texts(each_record) if is_assistant_record(each_record) else []
        if has_work_call([each_record]) or not all_record_texts:
            continue
        if split_footer(all_record_texts[-1]).footer_items is not None:
            start_position = each_position + 1
            break
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
    return [*assistant_texts(all_stretch_records[first_closing_position:]), *all_payload_texts]


def _missing_footer_lead(
    all_tasks: SessionTasks, is_declared: bool, did_work: bool
) -> str | None:
    if is_declared and all_tasks.in_progress:
        return IN_PROGRESS_TASKS_REASON_LEAD
    if did_work:
        return FOOTER_MISSING_REASON_LEAD
    return None


def footer_hold_reason(
    all_hook_input_fields: dict[str, object],
    closing_reply: str,
    did_work: bool,
    deadline_at: float,
) -> str | None:
    """Return the footer hold reason for the closing reply, or None when the reply may end.

    ::

        nothing in progress, no background work           -> None, no closing line owed
        "Open items: none."  task #28 in_progress          -> the declaration reason
        work, no footer, task #28 or background work       -> the missing-footer reason
        a footer that leaves out in-progress task #29      -> the gap reason
        a footer that names every in-progress task         -> None
        no work, no footer                                 -> None, a chat-only turn

    Args:
        all_hook_input_fields: The Stop payload, read for ``background_tasks``
            and the task list.
        closing_reply: The newest text after the last work call.
        did_work: Whether the stretch holds work after the last reply that
            ended with the footer.
        deadline_at: The monotonic time the declaration scan stops at.

    Returns:
        The reason, or None.
    """
    footer_items = split_footer(closing_reply).footer_items
    is_declared = footer_items is None and declares_no_open_items(closing_reply, deadline_at)
    if footer_items is None and not is_declared and not did_work:
        return None
    all_tasks = session_tasks(all_hook_input_fields)
    if not all_tasks.in_progress and not has_background_work(all_hook_input_fields):
        return None
    if footer_items is None:
        reason_lead = _missing_footer_lead(all_tasks, is_declared, did_work)
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
    all_question_items = [
        each_item
        for each_item in split_reply.footer_items
        if each_item.rstrip(TRAILING_MARKUP_CHARACTERS).endswith(QUESTION_MARK)
    ]
    return SCANNED_PARAGRAPH_SEPARATOR.join([split_reply.body, *all_question_items])


def _hold_reason(all_hook_input_fields: dict[str, object], deadline_at: float) -> str | None:
    covered_session = _covered_texts_and_records(all_hook_input_fields, deadline_at)
    if covered_session is None:
        return None
    all_payload_texts, all_stretch_records, all_counted_records = covered_session
    if prior_hold_count(all_counted_records) >= MAXIMUM_HOLD_COUNT:
        return None
    all_closing_texts = _closing_reply_texts(all_stretch_records, all_payload_texts)
    closing_reply = all_closing_texts[-1] if all_closing_texts else ""
    all_texts = [
        _scanned_text(each_text)
        for each_text in [*assistant_texts(all_stretch_records), *all_payload_texts]
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
    )


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
