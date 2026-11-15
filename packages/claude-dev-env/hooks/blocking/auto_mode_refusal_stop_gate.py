#!/usr/bin/env python3
"""Stop gate that holds a turn while a refused step waits on the user or on its rule.

At each turn end the gate reads the refusal ledger the PermissionDenied hook
keeps, and the session transcript::

    flow switch off, playbook missing, or print mode -> turn ends, no output
    answers read from transcript_path                -> answered entries leave the queue
    pending entry, not asked, held under 2 times     -> question hold, 4 groups at most
    allowed entry, no add call names it, held under 2 times -> rule hold
    none left                                        -> turn ends, no output
    a transcript it cannot read                      -> no calls seen, holds as above
    any other error                                  -> turn ends, no output
    reader closed stdout before the hold             -> exit 0, the hold text is dropped

An entry counts as asked once an answered ``AskUserQuestion`` call at or after
a question record's ``transcript_offset`` asks that record's exact text, with
any answer, or once a decision card call claims it. A card call that did not
fail and carries the card question ``Should auto mode have refused this <tool>
step?`` claims the oldest pending, unasked group of that tool that has an
entry with a question record at or before the card, and within it those
entries. Each card claims one
group, and the entry keeps the card's offset so a later Stop does not claim
again with it. The asked mark stays on the entry. An add call
is a Bash call that did not fail whose command holds ``add_auto_mode_rule.py
add`` and the entry's id, which its ledger file name carries. The gate keeps
its own counts in each entry file, so it acts the same whether or not
``stop_hook_active`` is set, and an entry holds four turns at most. A hold
exits 2 with a block object, through ``hold_stop``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

import auto_mode_refusal_ledger
from auto_mode_question_transcript import (
    AskedQuestions,
    TranscriptCall,
    read_asked_questions,
    read_tool_calls,
)
from auto_mode_refusal_ledger_files import (
    JsonObject,
    LedgerEntry,
    QuestionRecord,
    entry_file_path,
)
from hooks_constants.auto_mode_refusal_ledger_constants import (
    ALLOWED_ANSWER,
    QUESTION_ASKED_FIELD,
    QUESTION_CARD_OFFSET_FIELD,
    QUESTION_HOLDS_FIELD,
    RULE_HOLDS_FIELD,
)
from hooks_constants.auto_mode_refusal_stop_gate_constants import (
    ALL_CARD_TOOL_NAMES,
    ALLOW_EXIT_CODE,
    BASH_TOOL_NAME,
    CARD_QUESTION_TEMPLATE,
    COMMAND_INPUT_KEY,
    ENTRYPOINT_ENVIRONMENT_VARIABLE,
    LIST_LINE_TEMPLATE,
    MAXIMUM_HOLDS_PER_KIND,
    MAXIMUM_QUESTIONS_PER_HOLD,
    PRINT_MODE_ENTRYPOINT,
    QUESTION_BLOCK_TEMPLATE,
    QUESTION_SECTION_FOOTER_TEMPLATE,
    QUESTION_SECTION_HEADER,
    RULE_ADD_COMMAND_MARKER,
    RULE_SECTION_HEADER_TEMPLATE,
    SECTION_SEPARATOR,
    STOP_EVENT_NAME,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.stop_hook_hold import hold_stop


def _all_text_values(tool_input: object) -> list[str]:
    if isinstance(tool_input, str):
        return [tool_input]
    if isinstance(tool_input, dict):
        return [each for each_value in tool_input.values() for each in _all_text_values(each_value)]
    if isinstance(tool_input, list):
        return [each for each_value in tool_input for each in _all_text_values(each_value)]
    return []


def _is_card_for(call: TranscriptCall, tool_name: str) -> bool:
    return (
        call.tool_name in ALL_CARD_TOOL_NAMES
        and not call.is_error
        and CARD_QUESTION_TEMPLATE.format(tool_name=tool_name) in _all_text_values(call.tool_input)
    )


def _is_text_asked(record: QuestionRecord, all_asked: list[AskedQuestions]) -> bool:
    return any(
        each_asked.call_offset >= record.transcript_offset
        and record.question in each_asked.answer_by_question
        for each_asked in all_asked
    )


def _earliest_record_offset_by_id(all_records: list[QuestionRecord]) -> dict[str, int]:
    offset_by_id: dict[str, int] = {}
    for each_record in all_records:
        for each_id in each_record.all_entry_ids:
            offset_by_id[each_id] = min(
                offset_by_id.get(each_id, each_record.transcript_offset),
                each_record.transcript_offset,
            )
    return offset_by_id


def _card_offset_by_id(
    all_unasked_entries: list[LedgerEntry],
    all_records: list[QuestionRecord],
    all_calls: list[TranscriptCall],
    all_used_card_offsets: set[int | None],
) -> dict[str, int]:
    record_offset_by_id = _earliest_record_offset_by_id(all_records)
    card_offset_by_id: dict[str, int] = {}
    for each_call in all_calls:
        if each_call.call_offset in all_used_card_offsets:
            continue
        for each_group in auto_mode_refusal_ledger.question_groups(
            [each for each in all_unasked_entries if each.entry_id not in card_offset_by_id]
        ):
            all_card_ids = [
                each_id
                for each_id in each_group.all_entry_ids
                if each_id in record_offset_by_id
                and record_offset_by_id[each_id] <= each_call.call_offset
            ]
            if all_card_ids and _is_card_for(each_call, each_group.tool_name):
                card_offset_by_id.update(dict.fromkeys(all_card_ids, each_call.call_offset))
                break
    return card_offset_by_id


def _asked_entry_ids(
    ledger_directory: Path,
    all_entries: list[LedgerEntry],
    transcript_path: Path | None,
    all_calls: list[TranscriptCall],
) -> dict[str, int | None]:
    all_known_ids = {each.entry_id for each in all_entries}
    all_records = auto_mode_refusal_ledger.load_question_records(ledger_directory)
    all_asked = read_asked_questions(transcript_path)
    card_offset_by_id: dict[str, int | None] = {
        each_id: None
        for each_record in all_records
        if _is_text_asked(each_record, all_asked)
        for each_id in each_record.all_entry_ids
        if each_id in all_known_ids
    }
    all_unasked_entries = [
        each
        for each in all_entries
        if each.answer is None
        and not each.is_question_asked
        and each.entry_id not in card_offset_by_id
    ]
    card_offset_by_id.update(
        _card_offset_by_id(
            all_unasked_entries,
            all_records,
            all_calls,
            {each.question_card_offset for each in all_entries},
        )
    )
    return card_offset_by_id


def _has_add_call(entry: LedgerEntry, all_calls: list[TranscriptCall]) -> bool:
    for each_call in all_calls:
        if each_call.tool_name != BASH_TOOL_NAME or each_call.is_error:
            continue
        command = (
            each_call.tool_input.get(COMMAND_INPUT_KEY)
            if isinstance(each_call.tool_input, dict)
            else None
        )
        if (
            isinstance(command, str)
            and RULE_ADD_COMMAND_MARKER in command
            and entry.entry_id in command
        ):
            return True
    return False


def _could_hold(entry: LedgerEntry) -> bool:
    if entry.answer is None:
        return entry.question_holds < MAXIMUM_HOLDS_PER_KIND and not entry.is_question_asked
    return entry.answer == ALLOWED_ANSWER and entry.rule_holds < MAXIMUM_HOLDS_PER_KIND


def _ledger_lines(ledger_directory: Path, all_entry_ids: list[str]) -> str:
    return "".join(
        LIST_LINE_TEMPLATE.format(text=entry_file_path(ledger_directory, each_id))
        for each_id in all_entry_ids
    )


def hold_reason_for(
    all_groups: list[auto_mode_refusal_ledger.QuestionGroup],
    all_rule_entry_ids: list[str],
    ledger_directory: Path,
    playbook_path: Path,
) -> str:
    """Return the hold text for the questions to ask and the rules to add.

    ::

        one group, no rule entry -> header with the card question form,
                                    "Question: ...", steps, the order after
                                    Allow it, ledger files
        no group, one rule entry -> the playbook path and the ledger file

    Args:
        all_groups: The question groups to ask, four at most.
        all_rule_entry_ids: The allowed entries that still need a rule.
        ledger_directory: One session's ledger folder.
        playbook_path: The rule playbook the flow switch names.

    Returns:
        The question section, the rule section, or both.
    """
    all_sections: list[str] = []
    if all_groups:
        question_text = QUESTION_SECTION_HEADER
        for each_group in all_groups:
            question_text += QUESTION_BLOCK_TEMPLATE.format(question=each_group.question)
            question_text += "".join(
                LIST_LINE_TEMPLATE.format(text=each_summary)
                for each_summary in each_group.all_action_summaries
            )
        question_text += QUESTION_SECTION_FOOTER_TEMPLATE.format(playbook_path=playbook_path)
        question_text += _ledger_lines(
            ledger_directory,
            [each_id for each_group in all_groups for each_id in each_group.all_entry_ids],
        )
        all_sections.append(question_text)
    if all_rule_entry_ids:
        all_sections.append(
            RULE_SECTION_HEADER_TEMPLATE.format(playbook_path=playbook_path)
            + _ledger_lines(ledger_directory, all_rule_entry_ids)
        )
    return SECTION_SEPARATOR.join(all_sections)


def _flow_folders(all_stop_fields: dict[str, object]) -> tuple[Path, Path] | None:
    if os.environ.get(ENTRYPOINT_ENVIRONMENT_VARIABLE) == PRINT_MODE_ENTRYPOINT:
        return None
    playbook_path = auto_mode_refusal_ledger.playbook_path_from_environment()
    session_id = all_stop_fields.get("session_id")
    if playbook_path is None or not isinstance(session_id, str) or not session_id:
        return None
    ledger_directory = auto_mode_refusal_ledger.ledger_directory_for(session_id)
    if not ledger_directory.is_dir():
        return None
    return playbook_path, ledger_directory


def _counted_fields(
    all_entries: list[LedgerEntry],
    all_card_offset_by_asked_id: dict[str, int | None],
    all_groups: list[auto_mode_refusal_ledger.QuestionGroup],
    all_rule_entries: list[LedgerEntry],
) -> dict[str, JsonObject]:
    entry_by_id = {each.entry_id: each for each in all_entries}
    fields_by_entry_id: dict[str, JsonObject] = {
        each.entry_id: {QUESTION_ASKED_FIELD: True}
        for each in all_entries
        if each.entry_id in all_card_offset_by_asked_id and not each.is_question_asked
    }
    for each_id, each_card_offset in all_card_offset_by_asked_id.items():
        if each_card_offset is not None:
            fields_by_entry_id[each_id][QUESTION_CARD_OFFSET_FIELD] = each_card_offset
    for each_id in (each for each_group in all_groups for each in each_group.all_entry_ids):
        fields_by_entry_id.setdefault(each_id, {})[QUESTION_HOLDS_FIELD] = (
            entry_by_id[each_id].question_holds + 1
        )
    for each_entry in all_rule_entries:
        fields_by_entry_id.setdefault(each_entry.entry_id, {})[RULE_HOLDS_FIELD] = (
            each_entry.rule_holds + 1
        )
    return fields_by_entry_id


def _entries_to_hold(
    all_entries: list[LedgerEntry],
    all_asked_ids: dict[str, int | None],
    all_calls: list[TranscriptCall],
) -> tuple[list[auto_mode_refusal_ledger.QuestionGroup], list[LedgerEntry]]:
    all_groups = auto_mode_refusal_ledger.question_groups(
        [
            each
            for each in all_entries
            if each.answer is None and _could_hold(each) and each.entry_id not in all_asked_ids
        ]
    )[:MAXIMUM_QUESTIONS_PER_HOLD]
    all_rule_entries = [
        each
        for each in all_entries
        if each.answer == ALLOWED_ANSWER and _could_hold(each) and not _has_add_call(each, all_calls)
    ]
    return all_groups, all_rule_entries


def hold_reason_for_stop(all_stop_fields: dict[str, object]) -> str | None:
    """Return the hold text for one Stop payload, and record the hold in the ledger.

    Args:
        all_stop_fields: The Stop hook input JSON.

    Returns:
        The hold text, or None to let the turn end.
    """
    flow_folders = _flow_folders(all_stop_fields)
    if flow_folders is None:
        return None
    playbook_path, ledger_directory = flow_folders
    raw_transcript_path = all_stop_fields.get("transcript_path")
    transcript_path = Path(raw_transcript_path) if isinstance(raw_transcript_path, str) else None
    auto_mode_refusal_ledger.apply_transcript_answers(ledger_directory, transcript_path)
    all_entries = auto_mode_refusal_ledger.load_entries(ledger_directory)
    if not any(_could_hold(each) for each in all_entries):
        return None
    all_calls = read_tool_calls(transcript_path)
    all_asked_ids = _asked_entry_ids(ledger_directory, all_entries, transcript_path, all_calls)
    all_groups, all_rule_entries = _entries_to_hold(all_entries, all_asked_ids, all_calls)
    if all_groups:
        auto_mode_refusal_ledger.write_question_records(
            ledger_directory, all_groups, transcript_path
        )
    auto_mode_refusal_ledger.merge_entry_fields(
        ledger_directory, _counted_fields(all_entries, all_asked_ids, all_groups, all_rule_entries)
    )
    if not all_groups and not all_rule_entries:
        return None
    return hold_reason_for(
        all_groups, [each.entry_id for each in all_rule_entries], ledger_directory, playbook_path
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return ALLOW_EXIT_CODE
    if not isinstance(payload, dict):
        return ALLOW_EXIT_CODE
    try:
        hold_reason = hold_reason_for_stop(payload)
    except Exception:
        return ALLOW_EXIT_CODE
    if hold_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, STOP_EVENT_NAME, hold_reason)
    try:
        exit_code = hold_stop(payload, hold_reason)
        sys.stdout.flush()
    except OSError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return ALLOW_EXIT_CODE
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
