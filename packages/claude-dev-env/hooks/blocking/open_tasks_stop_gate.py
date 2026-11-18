#!/usr/bin/env python3
"""Stop hook that keeps the task list in step with the work an ask started.

The user follows a session's work in its task list. A turn that works on an ask
leaves a trace there: at least one tracker call after the prompt::

    TaskCreate / TaskUpdate        (Claude Code)
    TodoWrite                      (Claude Code and Cursor)
    update_plan                    (Codex)
    mcp__ccd_turn__update_plan     (Claude Code desktop plan)

The gate holds the turn once when all three hold::

    the prompt that started the turn asks for work   (open_task_asks.is_ask)
    the turn ran a work tool: any tool but a tracker call, the title tool,
        AskUserQuestion, a hearthbot decision card, ToolSearch, TaskList, TaskGet,
        or Codex request_user_input
    the turn made no tracker call

    block: "Export the APKs" -> Bash, Edit -> stop
    allow: "Export the APKs" -> TaskCreate, Bash, Edit -> stop
    allow: "did the export fail?" -> Bash -> stop
    allow: "Export the APKs" -> reply only -> stop
    allow: "Export the APKs" -> AskUserQuestion -> stop

A Claude Code session that has no tracker tool cannot act on that hold, so the
gate passes the turn when the transcript shows the session's tool lists and no
tracker in them::

    allow: prompt_snapshot tools and deferred_tools_delta name no tracker,
           and no deferred_tools_record or call names one
    block: a deferred_tools_delta lists TaskCreate, even when not yet loaded
    block: no prompt_snapshot tools list or no deferred_tools_delta (Codex, Cursor)

The user reads the task list to see what is open, so the gate also holds the
turn once when completed items sit beside open ones::

    block: 27 completed, 13 pending -> stop
    allow: 3 completed, none open   -> stop
    allow: 13 pending               -> stop

The list is the session's task store, or the transcript's list when the session
has no store. A list that ``CLAUDE_CODE_TASK_LIST_ID`` shares with other
sessions is left alone.

A turn that tells the user something waits on them reads the live state first
and hands over each step through the question tool. The gate reads the closing
reply and each Markdown, text, or HTML file the turn sent with SendUserFile, as
``user_step_wording.py`` describes, and holds the turn once::

    block: "Three items need you."  no read call this turn
    block: "Three items need you."  no question tool call this turn
    allow: the same reply after a read call and an AskUserQuestion call
    allow: "Both builds passed."
    allow: any reply when the transcript cannot be read

A read call is a shell, a file or web read, a subagent, or a tool whose name
carries a read word, as ``open_tasks_transcript.is_read_tool_name`` lists. The
gate checks that a read ran, and leaves which item it read to the agent. Each
such hold tells the agent to read the live state of every item it shows as
open, and to end the turn when the wording hands the user no step.

The closing reply also gets two checks of its own: a promised later report,
and open items sent as a list. On a Claude Code stop with ``claude`` on PATH,
one model call in ``closing_reply_judge.py`` reads the reply; Codex and Cursor
stops, and a host with no ``claude``, use the phrase checks that
``closing_reply_shapes.py`` describes. A judge that times out or gives no
usable verdict lets the stop go ahead. A stop inside a judge or review child
(``CLAUDE_TURN_REVIEW_CHILD=1``) goes ahead at once. The gate holds the turn
once::

    block: "The benchmark table will be posted when you get back."  no typed prompt asked for a report
    block: "What I deferred:" over 3 or more items             no question tool call this turn
    allow: the same list after an AskUserQuestion call
    allow: an "In progress:" footer over 9 items     the footer is cut off before both checks
    allow: the same promise after the prompt "report back when the run ends"
    allow: any reply when the transcript cannot be read

Such a hold names what it found and the steps, then one line that ends the
turn, then when the reply may stay as it is::

    promise only   -> "Then send the reworked reply and end the turn. Leave the promise as it is only when ..."
    list present   -> "Then send a short reply that names what you did and end the turn. Leave the list as it is only when ..."

One reason carries every finding. A Claude Code stop that a Stop hook already
held (``stop_hook_active``) gets only the closing-reply checks, and those hold
at most once per turn::

    block: another hook held, then "I'll report back once CI ends."   first such stop this turn
    allow: the same stop again                                          the turn's marker exists
    allow: a stop after this gate held the turn                         its feedback sits in the turn
    allow: a Codex turn, a prompt record with no ``uuid``, or a marker that cannot be kept

The marker is a file in the temp folder named for the session and the ``uuid``
of the prompt record that started the turn. A hold on the first stop writes it
too, so the gate costs at most one extra step per turn. The judge runs only
while the turn has no marker, so a stop after the hold makes no second call.

A hold exits with code 2 and writes the reason to stdout and stderr. Claude
Code marks a held stop with ``stop_hook_active``. Codex turns the reason into
a continuation prompt. A Cursor payload (it carries ``conversation_id``) exits
with code 0 and gets the reason as ``followup_message``, which Cursor submits
as the next user message; a Cursor stop whose ``loop_count`` shows a follow-up already sent
passes, and so does one whose ``status`` is ``aborted`` or ``error``. A TodoWrite
call that a Cursor ``CallDynamicTool`` call wraps counts as a TodoWrite call.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.final_reply_gate_constants import LAST_ASSISTANT_MESSAGE_KEY
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY
from hooks_constants.once_per_session_constants import SESSION_ID_KEY
from hooks_constants.stop_hook_hold import hold_stop
from once_per_session import claim_turn_showing, is_turn_claimed
from open_task_asks import claude_home, is_ask
from open_tasks_transcript import TaskItem, TranscriptReplay, normalized_text, parsed_object, replayed_transcript
from user_step_wording import file_waiting_phrase, waiting_phrase
from codex_continuation_review import continuation_review, user_requested_stop
from hooks_constants.codex_continuation_constants import AGENT_TRANSCRIPT_KEY, CHILD_FLAG, CHILD_STOP_EVENT
from closing_question_round_footer import split_footer
from closing_reply_shapes import item_count_under, open_item_list, promised_report_phrase
from closing_reply_judge import JudgeVerdict, is_judge_available, judged_verdict, log_no_verdict
from turn_review_transcript import _last_assistant_message_text, _ReversedTranscript
from hooks_constants.closing_reply_judge_constants import (
    MARKER_UNREADABLE_REASON,
    NO_TURN_KEY_REASON,
    TRANSCRIPT_UNREADABLE_REASON,
)
from hooks_constants.spawn_readiness_hook_constants import CODEX_TURN_ID_KEY
from hooks_constants.turn_review_gate_constants import REVIEW_CHILD_ENVIRONMENT_VARIABLE, REVIEW_CHILD_MARKER
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_OWN_REASON_OPENINGS,
    ALLOW_EXIT_CODE,
    CLOSING_REPLY_HOLD_MARKER_NAME,
    COMPLETED_ITEMS_REASON_TEMPLATE,
    COMPLETED_STATUS,
    CURSOR_COMPLETED_STATUS,
    CURSOR_CONVERSATION_ID_KEY,
    CURSOR_LOOP_COUNT_KEY,
    CURSOR_STATUS_KEY,
    HOOK_EVENT_NAME,
    INCOMPLETE_STATUSES,
    KEEP_REPLY_INSTRUCTION,
    NO_STEP_INSTRUCTION,
    OPEN_ITEM_LIST_KEEP_CONDITION,
    OPEN_ITEM_LIST_REASON_TEMPLATE,
    PROMISED_REPORT_KEEP_CONDITION,
    PROMISED_REPORT_REASON_TEMPLATE,
    REWORKED_REPLY_INSTRUCTION,
    SHORT_REPLY_INSTRUCTION,
    STOP_HOOK_ACTIVE_KEY,
    TASK_FILE_GLOB,
    TASK_ID_KEY,
    TASK_LIST_ID_ENVIRONMENT_VARIABLE,
    TASK_NUMBER_REFERENCE_TEMPLATE,
    TASK_STATUS_KEY,
    TASK_SUBJECT_KEY,
    TASKS_DIRECTORY_NAME,
    TRANSCRIPT_PATH_KEY,
    UNASKED_STEP_REASON,
    UNREAD_STEP_REASON,
    UNTRACKED_WORK_REASON,
    USER_STEP_LEAD_TEMPLATE,
    UTF8_ENCODING,
    WORD_SEPARATOR,
    WORKING_DIRECTORY_KEY,
)


def _task_file_item(task_file: Path) -> TaskItem | None:
    try:
        task_text = task_file.read_text(encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
    except OSError:
        return None
    all_task_fields = parsed_object(task_text)
    if all_task_fields is None:
        return None
    return TaskItem(
        str(all_task_fields.get(TASK_ID_KEY, task_file.stem)),
        str(all_task_fields.get(TASK_SUBJECT_KEY, "")),
        str(all_task_fields.get(TASK_STATUS_KEY, "")),
    )


def task_store_items(session_id: object) -> list[TaskItem] | None:
    """Return the task store items for the session, or None when no store exists."""
    task_list_id = os.environ.get(TASK_LIST_ID_ENVIRONMENT_VARIABLE) or session_id
    if not isinstance(task_list_id, str) or not task_list_id:
        return None
    task_directory = claude_home() / TASKS_DIRECTORY_NAME / task_list_id
    if not task_directory.is_dir():
        return None
    all_items = (_task_file_item(each_file) for each_file in sorted(task_directory.glob(TASK_FILE_GLOB)))
    return [each_item for each_item in all_items if each_item is not None]


def _subject_key(task_item: TaskItem) -> str:
    return normalized_text(task_item.subject) or TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=task_item.item_id)


def deduplicated_by_subject(all_sources: list[list[TaskItem]]) -> list[TaskItem]:
    """Drop an item whose subject an earlier source holds, so the task store wins over the transcript.

    The caller passes the task store and the whole transcript as two sources. Items inside one source all
    stay, so a pending task keeps its place beside a completed task of the same subject.
    """
    all_kept_items: list[TaskItem] = []
    all_earlier_keys: set[str] = set()
    for each_source in all_sources:
        all_kept_items.extend(each_item for each_item in each_source if _subject_key(each_item) not in all_earlier_keys)
        all_earlier_keys.update(_subject_key(each_item) for each_item in each_source)
    return all_kept_items


def session_task_items(session_id: object, replay: TranscriptReplay) -> list[TaskItem]:
    """Return the session's task list: the task store first, then transcript items it does not hold."""
    return deduplicated_by_subject([task_store_items(session_id) or [], replay.items() or []])


def is_untracked_work_turn(replay: TranscriptReplay) -> bool:
    """Return True when the turn worked on an ask and made no tracker call in a session that has a tracker."""
    if replay.lists_no_tracker_tool:
        return False
    return replay.has_turn_work_tool and not replay.has_turn_tracker_write and is_ask(replay.turn_prompt_text)


def shown_task_items(session_id: object, replay: TranscriptReplay) -> list[TaskItem]:
    """Return the task list the user sees: the task store when the session has one, else the transcript's list."""
    all_store_items = task_store_items(session_id)
    return all_store_items if all_store_items is not None else replay.items() or []


def stale_list_reason(all_items: list[TaskItem]) -> str | None:
    """Return the reason for completed items that sit beside open ones, or None.

    ::

        27 completed, 13 pending  -> reason naming 27 of 40 items
        3 completed, none open    -> None
        2 pending                 -> None
    """
    completed_count = sum(each_item.status == COMPLETED_STATUS for each_item in all_items)
    open_count = sum(each_item.status in INCOMPLETE_STATUSES for each_item in all_items)
    if not completed_count or not open_count:
        return None
    return COMPLETED_ITEMS_REASON_TEMPLATE.format(
        completed_count=completed_count, item_count=completed_count + open_count
    )


def turn_waiting_phrase(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> str | None:
    """Return the first phrase the closing reply or a sent text file uses to say something waits on the user; a path sent twice is read once."""
    reply_text = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    reply_phrase = waiting_phrase(reply_text) if isinstance(reply_text, str) else None
    if reply_phrase is not None:
        return reply_phrase
    working_directory = all_hook_input_fields.get(WORKING_DIRECTORY_KEY)
    all_file_phrases = (
        file_waiting_phrase(each_path, working_directory) for each_path in dict.fromkeys(replay.turn_sent_file_paths)
    )
    return next((each_phrase for each_phrase in all_file_phrases if each_phrase is not None), None)


def _has_readable_transcript(all_hook_input_fields: dict[str, object]) -> bool:
    transcript_path = all_hook_input_fields.get(TRANSCRIPT_PATH_KEY)
    return isinstance(transcript_path, str) and Path(transcript_path).is_file()


def user_step_reasons(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> list[str]:
    """Return a reason for each thing a turn skipped before it told the user something waits on them.

    ::

        "Three items need you.", no read call          -> the live read reason
        "Three items need you.", no question tool call -> the question tool reason
        the same reply after both calls                -> []
        "Both builds passed."                          -> []

    A session whose transcript cannot be read gives no reason.
    """
    if not _has_readable_transcript(all_hook_input_fields):
        return []
    all_reasons = [
        each_reason
        for each_reason, has_turn_call in (
            (UNREAD_STEP_REASON, replay.has_turn_read_tool),
            (UNASKED_STEP_REASON, replay.has_turn_question_tool),
        )
        if not has_turn_call
    ]
    if not all_reasons:
        return []
    phrase = turn_waiting_phrase(all_hook_input_fields, replay)
    return [] if phrase is None else [USER_STEP_LEAD_TEMPLATE.format(phrase=phrase), *all_reasons]


def tracker_reasons(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> list[str]:
    """Return a reason for untracked work, and one for completed items beside open ones on the session's own list."""
    all_reasons = [UNTRACKED_WORK_REASON] if is_untracked_work_turn(replay) else []
    if os.environ.get(TASK_LIST_ID_ENVIRONMENT_VARIABLE):
        return all_reasons
    stale_reason = stale_list_reason(shown_task_items(all_hook_input_fields.get(SESSION_ID_KEY), replay))
    return all_reasons if stale_reason is None else [*all_reasons, stale_reason]


class ClosingReplyFinding(NamedTuple):
    """One closing-reply shape the gate found: what it found and the steps, the line that ends the turn, and when to keep the reply."""

    reason: str
    closing_instruction: str
    keep_condition: str


def _promise_finding(promise_phrase: str) -> ClosingReplyFinding:
    return ClosingReplyFinding(
        PROMISED_REPORT_REASON_TEMPLATE.format(phrase=promise_phrase),
        REWORKED_REPLY_INSTRUCTION,
        PROMISED_REPORT_KEEP_CONDITION,
    )


def _list_finding(lead: str, item_count: int) -> ClosingReplyFinding:
    return ClosingReplyFinding(
        OPEN_ITEM_LIST_REASON_TEMPLATE.format(count=item_count, lead=lead),
        SHORT_REPLY_INSTRUCTION,
        OPEN_ITEM_LIST_KEEP_CONDITION,
    )


def is_judged_payload(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> bool:
    """Return True for a Claude Code stop on a host with ``claude`` on PATH, and False for Codex and Cursor stops.

    A Codex stop is one whose payload carries ``turn_id`` or whose turn a Codex rollout record started.
    """
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY) or all_hook_input_fields.get(CODEX_TURN_ID_KEY):
        return False
    if replay.is_codex_turn:
        return False
    return is_judge_available()


def _judged_reply_text(all_hook_input_fields: dict[str, object]) -> str:
    payload_reply = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    if isinstance(payload_reply, str) and payload_reply.strip():
        return split_footer(payload_reply).body
    return split_footer(_last_assistant_message_text(_ReversedTranscript(all_hook_input_fields))).body


def _verdict_findings(verdict: JudgeVerdict, reply_text: str) -> list[ClosingReplyFinding]:
    all_findings: list[ClosingReplyFinding] = []
    if verdict.promise_span:
        all_findings.append(_promise_finding(verdict.promise_span))
    if verdict.list_span:
        all_findings.append(_list_finding(verdict.list_span, item_count_under(reply_text, verdict.list_span)))
    return all_findings


def _judged_findings(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> list[ClosingReplyFinding]:
    if not _has_readable_transcript(all_hook_input_fields):
        log_no_verdict(TRANSCRIPT_UNREADABLE_REASON)
        return []
    if replay.turn_key is None:
        log_no_verdict(NO_TURN_KEY_REASON)
        return []
    is_claimed = is_turn_claimed(CLOSING_REPLY_HOLD_MARKER_NAME, all_hook_input_fields, replay.turn_key)
    if is_claimed is None:
        log_no_verdict(MARKER_UNREADABLE_REASON)
    if is_claimed is not False:
        return []
    reply_text = _judged_reply_text(all_hook_input_fields)
    if not reply_text:
        return []
    verdict = judged_verdict(replay.turn_prompt_text, reply_text, replay.has_turn_question_tool)
    return [] if verdict is None else _verdict_findings(verdict, reply_text)


def closing_reply_findings(
    all_hook_input_fields: dict[str, object], replay: TranscriptReplay
) -> list[ClosingReplyFinding]:
    """Return a finding for a promised later report and one for open items sent as a list in the closing reply.

    ::

        "The benchmark table will be posted when you get back."   -> the promised report finding
        "What I deferred:" over 5 items, no question call    -> the open item list finding
        the same list after an AskUserQuestion call          -> []

    A Claude Code stop on a host with ``claude`` on PATH asks the judge in
    ``closing_reply_judge.py`` once, and only while this turn holds no
    closing-reply hold yet. Its reply is ``last_assistant_message``, or the
    transcript's last assistant text when that field is empty. A judge that
    gives no verdict gives no finding. Codex and Cursor stops, and a host with
    no ``claude``, use the phrase checks in ``closing_reply_shapes.py``. A
    session whose transcript cannot be read gives no finding. Both read the
    reply with its In progress footer cut off, as
    ``closing_question_round_footer.split_footer`` cuts it, because the footer
    is a status list that ``closing_question_round_gate.py`` checks.
    """
    if is_judged_payload(all_hook_input_fields, replay):
        return _judged_findings(all_hook_input_fields, replay)
    payload_reply = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(payload_reply, str) or not _has_readable_transcript(all_hook_input_fields):
        return []
    reply_text = split_footer(payload_reply).body
    all_findings: list[ClosingReplyFinding] = []
    promise_phrase = promised_report_phrase(reply_text, replay.turn_prompt_text)
    if promise_phrase is not None:
        all_findings.append(_promise_finding(promise_phrase))
    item_list = None if replay.has_turn_question_tool else open_item_list(reply_text, replay.turn_prompt_text)
    if item_list is not None:
        all_findings.append(_list_finding(item_list.lead, item_list.item_count))
    return all_findings


def _closing_lines(has_step_reason: bool, all_reply_findings: list[ClosingReplyFinding]) -> list[str]:
    if all_reply_findings:
        return [
            all_reply_findings[-1].closing_instruction,
            *(each_finding.keep_condition for each_finding in all_reply_findings),
        ]
    return [NO_STEP_INSTRUCTION if has_step_reason else KEEP_REPLY_INSTRUCTION]


def turn_block_reason(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> str | None:
    """Return one reason that carries every finding on the turn, or None when the turn may end.

    ::

        tracker finding only           -> the finding, then "Then end the turn. Leave the reply as it stands."
        promise and list findings      -> both findings, the list's closing line, then both keep conditions

    A Codex continuation asks for the next authorized step when the closing text still describes unfinished work.
    """
    all_tracker_reasons = tracker_reasons(all_hook_input_fields, replay)
    all_step_reasons = user_step_reasons(all_hook_input_fields, replay)
    all_reply_findings = closing_reply_findings(all_hook_input_fields, replay)
    all_reasons = [
        *all_tracker_reasons,
        *all_step_reasons,
        *(each_finding.reason for each_finding in all_reply_findings),
    ]
    if (all_hook_input_fields.get(CODEX_TURN_ID_KEY) or replay.is_codex_turn) and not all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        review = continuation_review(all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY), replay.turn_prompt_text, replay.has_turn_question_tool)
        if review:
            return WORD_SEPARATOR.join([*all_reasons, review])
    if not all_reasons:
        return None
    return WORD_SEPARATOR.join([*all_reasons, *_closing_lines(bool(all_step_reasons), all_reply_findings)])


def _closing_reply_reason(all_reply_findings: list[ClosingReplyFinding]) -> str:
    return WORD_SEPARATOR.join(
        [*(each_finding.reason for each_finding in all_reply_findings), *_closing_lines(False, all_reply_findings)]
    )


def _has_turn_hold_from_this_gate(replay: TranscriptReplay) -> bool:
    return any(
        each_opening in each_feedback
        for each_feedback in replay.turn_stop_feedback_texts
        for each_opening in ALL_OWN_REASON_OPENINGS
    )


def continued_stop_reason(all_hook_input_fields: dict[str, object], replay: TranscriptReplay) -> str | None:
    """Return the closing-reply reason for a Claude Code stop that a Stop hook already held, at most once per turn.

    ::

        another hook held, the reply promises a report, first time this turn  -> the promised report reason
        the same turn again                                                    -> None
        a stop after this gate held the turn                                   -> None
        no turn key, a Cursor payload, or a marker that cannot be kept         -> None

    The turn key is the ``uuid`` of the prompt record that started the turn.
    Tracker and user-step reasons stay off such a stop.
    """
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY) or replay.turn_key is None:
        return None
    if _has_turn_hold_from_this_gate(replay):
        return None
    all_reply_findings = closing_reply_findings(all_hook_input_fields, replay)
    if not all_reply_findings:
        return None
    if claim_turn_showing(CLOSING_REPLY_HOLD_MARKER_NAME, all_hook_input_fields, replay.turn_key) is not True:
        return None
    return _closing_reply_reason(all_reply_findings)


def is_held_stop(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True when a stop hook already held this turn once, or the Cursor run did not complete."""
    if all_hook_input_fields.get(STOP_HOOK_ACTIVE_KEY) is True:
        return True
    if not all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        return False
    stop_status = all_hook_input_fields.get(CURSOR_STATUS_KEY)
    loop_count = all_hook_input_fields.get(CURSOR_LOOP_COUNT_KEY)
    has_sent_followup = isinstance(loop_count, int) and loop_count > 0
    return has_sent_followup or (stop_status is not None and stop_status != CURSOR_COMPLETED_STATUS)


def _stop_block_reason(all_hook_input_fields: dict[str, object]) -> str | None:
    if os.environ.get(REVIEW_CHILD_ENVIRONMENT_VARIABLE) == REVIEW_CHILD_MARKER:
        return None
    is_claude_held_stop = all_hook_input_fields.get(STOP_HOOK_ACTIVE_KEY) is True
    if is_held_stop(all_hook_input_fields) and not is_claude_held_stop:
        return None
    replay = replayed_transcript(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY))
    if replay.is_codex_turn and user_requested_stop(replay.turn_prompt_text):
        return None
    if is_claude_held_stop:
        if all_hook_input_fields.get(CODEX_TURN_ID_KEY) or replay.is_codex_turn:
            return None
        return continued_stop_reason(all_hook_input_fields, replay)
    block_reason = turn_block_reason(all_hook_input_fields, replay)
    if block_reason is not None and replay.turn_key is not None:
        claim_turn_showing(CLOSING_REPLY_HOLD_MARKER_NAME, all_hook_input_fields, replay.turn_key)
    return block_reason


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    is_child_stop = sys.argv[1:] == [CHILD_FLAG]
    if is_child_stop:
        if hook_input.get("hook_event_name") != CHILD_STOP_EVENT or is_held_stop(hook_input):
            return ALLOW_EXIT_CODE
        child_turn = replayed_transcript(hook_input.get(AGENT_TRANSCRIPT_KEY))
        block_reason = continuation_review(hook_input.get(LAST_ASSISTANT_MESSAGE_KEY), child_turn.turn_prompt_text, child_turn.has_turn_question_tool)
    else:
        block_reason = _stop_block_reason(hook_input)
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, CHILD_STOP_EVENT if is_child_stop else HOOK_EVENT_NAME, block_reason)
    return hold_stop(hook_input, block_reason)


if __name__ == "__main__":
    sys.exit(main())
