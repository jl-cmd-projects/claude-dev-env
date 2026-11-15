"""The auto mode refusal ledger: refused steps, their questions, their answers.

One session's ledger is a folder of JSON files::

    <config>/state/auto-mode-refusals/<session_id>/
        3f9a0c1d2e4b5a6c.json            one refused step, "answer": null
        question-8d7e6f5a4b3c2d1e.json   one question text and the ids it covers

A step's id comes from its tool name and full ``tool_input``, so the same
refusal twice is one entry and two edits of one file are two. Pending entries
group by tool name and exact rule label, and one question covers up to the
five oldest of a group. An answer counts only when an ``AskUserQuestion``
call that starts at or after the record's ``transcript_offset`` asks the
record's exact question text and gets ``Allow it`` or ``Keep refusing``.
``auto_mode_refusal_ledger_files.py`` reads each file into a typed entry or
record and skips a file that does not parse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from auto_mode_question_transcript import AskedQuestions, read_asked_questions
from auto_mode_refusal_ledger_files import (
    JsonObject,
    LedgerEntry,
    QuestionRecord,
    entry_file_path,
    entry_id_for,
    ledger_directory_for,
    load_entries,
    load_question_records,
    parse_entry,
    parse_question_record,
    question_file_path,
    read_json_object,
    write_json_object,
)
from auto_mode_rule_steps import RuleFlowSetting, is_rule_flow_step
from hooks_constants.auto_mode_refusal_ledger_constants import (
    ALL_RULE_ROOT_MARKER_PATHS,
    ALLOWED_ANSWER,
    ANSWER_BY_OPTION_LABEL,
    MAXIMUM_STEPS_PER_QUESTION,
    PLAYBOOK_ENVIRONMENT_VARIABLE,
    PLAYBOOK_ROOT_DEPTH,
    QUESTION_RECORD_KIND,
    SEVERAL_STEPS_QUESTION_TEMPLATE,
    SINGLE_STEP_QUESTION_TEMPLATE,
    TIMESTAMP_FORMAT,
)


@dataclass(frozen=True)
class QuestionGroup:
    """One question the user is asked about a group of pending entries.

    Attributes:
        question: The exact question text.
        tool_name: The tool every entry in the group used.
        rule_label: The rule label every entry in the group was refused under.
        all_entry_ids: The ids the question covers, oldest first.
        all_action_summaries: One short line per covered step, oldest first.
    """

    question: str
    tool_name: str
    rule_label: str
    all_entry_ids: tuple[str, ...]
    all_action_summaries: tuple[str, ...]


@dataclass(frozen=True)
class RefusedStep:
    """One refusal as the PermissionDenied hook hands it to the ledger.

    Attributes:
        session_id: The session id from the hook input.
        transcript_path: The session transcript, or None when unknown.
        tool_name: The refused call's tool name.
        tool_input: The refused call's full ``tool_input``.
        working_folder: The ``cwd`` from the hook input, or None.
        rule_label: The parsed rule label, or None for a reason with none.
        reason: The refusal reason on one display line.
        action_summary: One short line that names the step.
    """

    session_id: str
    transcript_path: Path | None
    tool_name: str
    tool_input: object
    working_folder: str | None
    rule_label: str | None
    reason: str
    action_summary: str


def playbook_path_from_environment() -> Path | None:
    """Return the rule playbook path when the flow switch names an existing file.

    Returns:
        The path ``CLAUDE_AUTO_MODE_RULE_PLAYBOOK`` names, or None when the
        variable is unset or empty or the file does not exist.
    """
    configured_path = os.environ.get(PLAYBOOK_ENVIRONMENT_VARIABLE, "")
    if not configured_path or not Path(configured_path).is_file():
        return None
    return Path(configured_path)


def rule_repository_root(playbook_path: Path) -> Path | None:
    """Return the repository that holds the rule playbook.

    ::

        /work/agent-channels/docs/auto-mode-rule.md -> /work/agent-channels
            (it holds .git and setup/add_auto_mode_rule.py)
        /docs/auto-mode-rule.md                     -> None, / holds no rule tool
        /auto-mode-rule.md                          -> None

    Args:
        playbook_path: The rule playbook the flow switch names.

    Returns:
        The folder two levels above the resolved playbook when it holds
        ``.git`` and ``setup/add_auto_mode_rule.py``, else None.
    """
    all_parent_folders = playbook_path.resolve().parents
    if len(all_parent_folders) < PLAYBOOK_ROOT_DEPTH:
        return None
    repository_root = all_parent_folders[PLAYBOOK_ROOT_DEPTH - 1]
    if not all((repository_root / each).exists() for each in ALL_RULE_ROOT_MARKER_PATHS):
        return None
    return repository_root


def question_text_for(tool_name: str, rule_label: str, step_count: int) -> str:
    """Return the exact question for a group of refused steps.

    ::

        Bash, Git Destructive, 1 -> "Auto mode refused 1 Bash step under the
                                     Git Destructive rule. Should auto mode
                                     have refused it?"
        Bash, Git Destructive, 2 -> "... 2 Bash steps ... refused them?"

    Args:
        tool_name: The tool the steps used.
        rule_label: The rule label they were refused under.
        step_count: How many steps the question covers.

    Returns:
        The question text.
    """
    if step_count == 1:
        return SINGLE_STEP_QUESTION_TEMPLATE.format(tool_name=tool_name, rule_label=rule_label)
    return SEVERAL_STEPS_QUESTION_TEMPLATE.format(
        step_count=step_count, tool_name=tool_name, rule_label=rule_label
    )


def add_entry(ledger_directory: Path, entry_fields: JsonObject) -> bool:
    """Write one pending entry unless an entry with its id exists.

    Args:
        ledger_directory: One session's ledger folder.
        entry_fields: The entry's fields; ``id`` names the file.

    Returns:
        Whether a new entry file was written.
    """
    entry_path = entry_file_path(ledger_directory, str(entry_fields["id"]))
    if entry_path.exists():
        return False
    all_sequences = [each.sequence for each in load_entries(ledger_directory)]
    write_json_object(
        entry_path,
        {
            **entry_fields,
            "sequence": max(all_sequences, default=0) + 1,
            "refused_at": datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT),
            "answer": None,
        },
    )
    return True


def question_groups(all_entries: list[LedgerEntry]) -> list[QuestionGroup]:
    """Return the questions the pending entries need, in order of first refusal.

    ::

        pending Bash/Git Destructive x2, WebFetch/Data Exfiltration x1
            -> "2 Bash steps ... Git Destructive", "1 WebFetch step ... Data Exfiltration"
        pending Bash/Git Destructive x7 -> one question for the five oldest

    Args:
        all_entries: The ledger entries, oldest first.

    Returns:
        One group per tool name and exact rule label that has a pending entry.
    """
    pending_by_group: dict[tuple[str, str], list[LedgerEntry]] = {}
    for each_entry in all_entries:
        if each_entry.answer is None:
            group_key = (each_entry.tool_name, each_entry.rule_label)
            pending_by_group.setdefault(group_key, []).append(each_entry)
    return [
        QuestionGroup(
            question=question_text_for(each_tool_name, each_rule_label, len(each_covered)),
            tool_name=each_tool_name,
            rule_label=each_rule_label,
            all_entry_ids=tuple(each.entry_id for each in each_covered),
            all_action_summaries=tuple(each.action_summary for each in each_covered),
        )
        for (each_tool_name, each_rule_label), each_group_entries in pending_by_group.items()
        if (each_covered := each_group_entries[:MAXIMUM_STEPS_PER_QUESTION])
    ]


def _transcript_size(transcript_path: Path | None) -> int:
    if transcript_path is None:
        return 0
    try:
        return transcript_path.stat().st_size
    except OSError:
        return 0


def write_question_records(
    ledger_directory: Path, all_groups: list[QuestionGroup], transcript_path: Path | None
) -> None:
    """Write one question record per group, the one writer both hooks use.

    ::

        question-<digest>.json
        {"record": "question", "question": "<exact text>",
         "entry_ids": ["3f9a..."], "tool_name": "Bash",
         "rule_label": "Git Destructive", "transcript_offset": 18233,
         "written_at": "2026-11-15T14:02:11.120000Z"}

    A record whose text already covers the same ids stays as it is, so its
    ``transcript_offset`` keeps the transcript size from its first write. A
    record whose ids changed, or that does not parse, is rewritten with the
    current size. Asks that start before the offset never answer it.

    Args:
        ledger_directory: One session's ledger folder.
        all_groups: The groups from ``question_groups``.
        transcript_path: The session transcript, or None when unknown.
    """
    for each_group in all_groups:
        question_path = question_file_path(ledger_directory, each_group.question)
        existing_record = parse_question_record(read_json_object(question_path))
        if existing_record and existing_record.all_entry_ids == each_group.all_entry_ids:
            continue
        write_json_object(
            question_path,
            {
                "record": QUESTION_RECORD_KIND,
                "question": each_group.question,
                "tool_name": each_group.tool_name,
                "rule_label": each_group.rule_label,
                "entry_ids": list(each_group.all_entry_ids),
                "transcript_offset": _transcript_size(transcript_path),
                "written_at": datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT),
            },
        )


def _answer_for(record: QuestionRecord, all_asked: list[AskedQuestions]) -> str | None:
    for each_asked in all_asked:
        if each_asked.call_offset < record.transcript_offset:
            continue
        answer = ANSWER_BY_OPTION_LABEL.get(each_asked.answer_by_question.get(record.question, ""))
        if answer is not None:
            return answer
    return None


def apply_transcript_answers(ledger_directory: Path, transcript_path: Path | None) -> None:
    """Set the answer of each pending entry whose question the user answered.

    ::

        record "Auto mode refused 1 Bash step ...", ids [a], offset 900
        ask at offset 1200 with that exact text, answer "Allow it" -> a: "allowed"
        ask at offset 400 with that exact text                     -> ignored
        ask with other text, or answer "allow it"                  -> ignored

    Only ids a record names change, and only while their answer is null.

    Args:
        ledger_directory: One session's ledger folder.
        transcript_path: The session transcript, or None.
    """
    all_records = load_question_records(ledger_directory)
    if not all_records:
        return
    all_asked = read_asked_questions(transcript_path)
    for each_record in all_records:
        answer = _answer_for(each_record, all_asked)
        if answer is not None:
            _set_pending_answers(ledger_directory, each_record.all_entry_ids, answer)


def _set_pending_answers(
    ledger_directory: Path, all_entry_ids: tuple[str, ...], answer: str
) -> None:
    for each_entry_id in all_entry_ids:
        entry_path = entry_file_path(ledger_directory, each_entry_id)
        raw_entry = read_json_object(entry_path)
        parsed_entry = parse_entry(raw_entry)
        if raw_entry is not None and parsed_entry is not None and parsed_entry.answer is None:
            write_json_object(entry_path, {**raw_entry, "answer": answer})


def merge_entry_fields(
    ledger_directory: Path, fields_by_entry_id: dict[str, JsonObject]
) -> None:
    """Merge new fields into existing entry files and keep every other field.

    ::

        {"3f9a...": {"question_holds": 1}} -> 3f9a....json gains question_holds 1
        an id with no file, or a file that does not parse -> nothing written

    Args:
        ledger_directory: One session's ledger folder.
        fields_by_entry_id: The fields to set, by entry id.
    """
    for each_entry_id, each_fields in fields_by_entry_id.items():
        entry_path = entry_file_path(ledger_directory, each_entry_id)
        raw_entry = read_json_object(entry_path)
        if raw_entry is not None and parse_entry(raw_entry) is not None:
            write_json_object(entry_path, {**raw_entry, **each_fields})


def _entry_fields_for(step: RefusedStep, rule_label: str) -> JsonObject:
    return {
        "id": entry_id_for(step.tool_name, step.tool_input),
        "session_id": step.session_id,
        "tool_name": step.tool_name,
        "tool_input": step.tool_input,
        "rule_label": rule_label,
        "reason": step.reason,
        "action_summary": step.action_summary,
        "cwd": step.working_folder,
    }


def record_refusal(step: RefusedStep, repository_root: Path) -> str | None:
    """Keep the refusal ledger for one denial and return the question to ask.

    ::

        "[Git Destructive] force push", new step -> entry written,
            "Auto mode refused 1 Bash step under the Git Destructive rule. ..."
        same step again                          -> no new entry, same question
        prose reason, or a rule flow step        -> None

    The user's answers are read from the transcript before the skip rule, so
    an entry answered in this turn already reads ``allowed``.

    Args:
        step: The refusal, parsed by the PermissionDenied hook.
        repository_root: The repository that holds the rule playbook.

    Returns:
        The exact question for the group that holds this step while the
        step is pending, else None.
    """
    ledger_directory = ledger_directory_for(step.session_id)
    apply_transcript_answers(ledger_directory, step.transcript_path)
    if step.rule_label is None:
        return None
    has_allowed_entry = any(
        each.answer == ALLOWED_ANSWER for each in load_entries(ledger_directory)
    )
    setting = RuleFlowSetting(repository_root, has_allowed_entry)
    if is_rule_flow_step(step.tool_name, step.tool_input, step.working_folder, setting):
        return None
    entry_fields = _entry_fields_for(step, step.rule_label)
    add_entry(ledger_directory, entry_fields)
    all_groups = question_groups(load_entries(ledger_directory))
    write_question_records(ledger_directory, all_groups, step.transcript_path)
    return next(
        (
            each_group.question
            for each_group in all_groups
            if entry_fields["id"] in each_group.all_entry_ids
        ),
        None,
    )
