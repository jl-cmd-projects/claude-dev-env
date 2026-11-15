"""Where the refusal ledger's files live, and how they are read and written.

A session's ledger folder sits under the config folder, and a step's id names
its file. Each JSON file in a session's ledger folder is parsed when it is read::

    {"id": "3f9a...", "tool_name": "Bash", "rule_label": "Git Destructive",
     "sequence": 1, "answer": null, ...}              -> LedgerEntry
    {"record": "question", "question": "...",
     "entry_ids": ["3f9a..."], "transcript_offset": 900} -> QuestionRecord
    {"answer": null} with no id, or "sequence": "first" -> None, skipped

A file that does not parse never raises, so one bad file cannot stop the
refusal hook or the Stop gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from atomic_file_writer import write_text_atomically
from hooks_constants.auto_mode_refusal_ledger_constants import (
    ALL_ANSWERS,
    ALL_LEDGER_RELATIVE_PARTS,
    ENTRY_FILE_SUFFIX,
    ID_HEX_CHARACTERS,
    JSON_INDENT_SPACES,
    QUESTION_ASKED_FIELD,
    QUESTION_CARD_OFFSET_FIELD,
    QUESTION_FILE_PREFIX,
    QUESTION_HOLDS_FIELD,
    QUESTION_RECORD_KIND,
    RULE_HOLDS_FIELD,
    TEMPORARY_FILE_PREFIX,
    TEMPORARY_FILE_SUFFIX,
    TEXT_ENCODING,
)
from open_task_asks import claude_home

JsonObject = dict[str, object]


@dataclass(frozen=True)
class LedgerEntry:
    """One refused step read from its ledger file.

    Attributes:
        entry_id: The step's id, which also names its file.
        tool_name: The refused call's tool name.
        rule_label: The rule label the step was refused under.
        action_summary: One short line that names the step.
        sequence: The step's place in refusal order.
        answer: ``allowed``, ``kept``, or None while the step is pending.
        question_holds: How many turns the Stop gate held to ask about it.
        rule_holds: How many turns the Stop gate held for its rule.
        is_question_asked: Whether the Stop gate saw its question asked.
        question_card_offset: The transcript offset of the decision card
            that asked it, or None when no card asked it.
    """

    entry_id: str
    tool_name: str
    rule_label: str
    action_summary: str
    sequence: int
    answer: str | None
    question_holds: int = 0
    rule_holds: int = 0
    is_question_asked: bool = False
    question_card_offset: int | None = None


@dataclass(frozen=True)
class QuestionRecord:
    """One question record read from its ledger file.

    Attributes:
        question: The exact question text.
        all_entry_ids: The ids the question covers.
        transcript_offset: The transcript size when the record was written.
    """

    question: str
    all_entry_ids: tuple[str, ...]
    transcript_offset: int


def ledger_directory_for(session_id: str) -> Path:
    """Return the folder that holds one session's ledger.

    Args:
        session_id: The session id from the hook input.

    Returns:
        ``<config>/state/auto-mode-refusals/<session_id>``. A character
        outside letters, digits, ``-`` and ``_`` becomes ``_`` in the name.
    """
    safe_session_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id) or "_"
    return claude_home().joinpath(*ALL_LEDGER_RELATIVE_PARTS, safe_session_id)


def entry_id_for(tool_name: str, tool_input: object) -> str:
    """Return the ledger id of one refused step.

    ::

        Edit {"file_path": "a.py", "old_string": "x"} -> one id
        Edit {"file_path": "a.py", "old_string": "y"} -> another id

    Args:
        tool_name: The refused call's tool name.
        tool_input: The refused call's full ``tool_input``.

    Returns:
        The first hex characters of a SHA-256 over both, as sorted JSON.
    """
    identity_text = json.dumps(
        {"tool_name": tool_name, "tool_input": tool_input}, sort_keys=True, default=str
    )
    return hashlib.sha256(identity_text.encode(TEXT_ENCODING)).hexdigest()[:ID_HEX_CHARACTERS]



def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_count(value: object) -> bool:
    return _is_integer(value) and value >= 0


def read_json_object(file_path: Path) -> JsonObject | None:
    """Return the JSON object a file holds, or None.

    Args:
        file_path: One ledger file.

    Returns:
        The object, or None when the file cannot be read, is not JSON, or
        holds something other than an object.
    """
    try:
        parsed_file = json.loads(file_path.read_text(encoding=TEXT_ENCODING))
    except (OSError, ValueError):
        return None
    return parsed_file if isinstance(parsed_file, dict) else None


def parse_entry(json_object: JsonObject | None) -> LedgerEntry | None:
    """Return the entry a ledger file's object describes, or None.

    Args:
        json_object: The object from ``read_json_object``.

    Returns:
        The entry when the object has an ``answer`` key, text ``id``,
        ``tool_name``, ``rule_label`` and ``action_summary``, an integer
        ``sequence``, and an answer that is null, ``allowed`` or ``kept``.
        The Stop gate's ``question_holds`` and ``rule_holds`` default to 0
        and must be integers of 0 or more, ``question_asked`` defaults to
        false and must be a boolean, and ``question_card_offset`` defaults
        to null and must be null or an integer of 0 or more.
    """
    if json_object is None or "answer" not in json_object:
        return None
    all_text_fields = [json_object.get(each) for each in ("id", "tool_name", "rule_label")]
    all_text_fields.append(json_object.get("action_summary", ""))
    sequence = json_object.get("sequence", 0)
    all_hold_counts = [
        json_object.get(each_name, 0) for each_name in (QUESTION_HOLDS_FIELD, RULE_HOLDS_FIELD)
    ]
    answer = json_object["answer"]
    is_question_asked = json_object.get(QUESTION_ASKED_FIELD, False)
    question_card_offset = json_object.get(QUESTION_CARD_OFFSET_FIELD)
    if not (
        all(isinstance(each, str) for each in all_text_fields)
        and _is_integer(sequence)
        and all(_is_count(each) for each in all_hold_counts)
        and (answer is None or answer in ALL_ANSWERS)
        and isinstance(is_question_asked, bool)
        and (question_card_offset is None or _is_count(question_card_offset))
    ):
        return None
    entry_id, tool_name, rule_label, action_summary = all_text_fields
    question_holds, rule_holds = all_hold_counts
    return LedgerEntry(
        entry_id, tool_name, rule_label, action_summary, sequence, answer,
        question_holds, rule_holds, is_question_asked, question_card_offset,
    )


def parse_question_record(json_object: JsonObject | None) -> QuestionRecord | None:
    """Return the question record a ledger file's object describes, or None.

    Args:
        json_object: The object from ``read_json_object``.

    Returns:
        The record when the object is a question record with text
        ``question``, a list of text ``entry_ids`` and an integer
        ``transcript_offset``.
    """
    if json_object is None or json_object.get("record") != QUESTION_RECORD_KIND:
        return None
    question = json_object.get("question")
    all_entry_ids = json_object.get("entry_ids")
    transcript_offset = json_object.get("transcript_offset", 0)
    if not (
        isinstance(question, str)
        and isinstance(all_entry_ids, list)
        and all(isinstance(each, str) for each in all_entry_ids)
        and _is_integer(transcript_offset)
    ):
        return None
    return QuestionRecord(question, tuple(all_entry_ids), transcript_offset)


def write_json_object(file_path: Path, json_object: JsonObject) -> None:
    """Write one ledger file atomically, as sorted, indented JSON.

    Args:
        file_path: The ledger file to write.
        json_object: The object to write.
    """
    write_text_atomically(
        file_path,
        json.dumps(json_object, indent=JSON_INDENT_SPACES, sort_keys=True) + "\n",
        TEXT_ENCODING,
        TEMPORARY_FILE_PREFIX,
        TEMPORARY_FILE_SUFFIX,
        should_reap_orphans=False,
    )


def entry_file_path(ledger_directory: Path, entry_id: str) -> Path:
    """Return the file that holds one entry.

    Args:
        ledger_directory: One session's ledger folder.
        entry_id: The entry's id.

    Returns:
        ``<ledger_directory>/<entry_id>.json``.
    """
    return ledger_directory / f"{entry_id}{ENTRY_FILE_SUFFIX}"


def question_file_path(ledger_directory: Path, question: str) -> Path:
    """Return the file that holds the record of one question text.

    Args:
        ledger_directory: One session's ledger folder.
        question: The exact question text.

    Returns:
        ``<ledger_directory>/question-<digest>.json``.
    """
    question_digest = hashlib.sha256(question.encode(TEXT_ENCODING)).hexdigest()
    return (
        ledger_directory
        / f"{QUESTION_FILE_PREFIX}{question_digest[:ID_HEX_CHARACTERS]}{ENTRY_FILE_SUFFIX}"
    )


def load_entries(ledger_directory: Path) -> list[LedgerEntry]:
    """Return every refused-step entry in a ledger folder, oldest first.

    Args:
        ledger_directory: One session's ledger folder.

    Returns:
        The entries that parse, sorted by their ``sequence`` number. A file
        that ``parse_entry`` rejects, or whose name is not ``<id>.json`` for
        the id it holds, is skipped.
    """
    if not ledger_directory.is_dir():
        return []
    all_entries = [
        each_entry
        for each_path in ledger_directory.glob(f"*{ENTRY_FILE_SUFFIX}")
        if (each_entry := parse_entry(read_json_object(each_path))) is not None
        and each_path == entry_file_path(ledger_directory, each_entry.entry_id)
    ]
    return sorted(all_entries, key=lambda each_entry: each_entry.sequence)


def load_question_records(ledger_directory: Path) -> list[QuestionRecord]:
    """Return every question record in a ledger folder, in file name order.

    Args:
        ledger_directory: One session's ledger folder.

    Returns:
        The records that parse. A file that ``parse_question_record``
        rejects is skipped.
    """
    if not ledger_directory.is_dir():
        return []
    return [
        each_record
        for each_path in sorted(
            ledger_directory.glob(f"{QUESTION_FILE_PREFIX}*{ENTRY_FILE_SUFFIX}")
        )
        if (each_record := parse_question_record(read_json_object(each_path))) is not None
    ]
