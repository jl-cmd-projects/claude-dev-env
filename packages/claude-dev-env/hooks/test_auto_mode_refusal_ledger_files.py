"""Behavior tests for reading and writing the refusal ledger's files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import auto_mode_refusal_ledger_files as ledger_files


@pytest.fixture(autouse=True)
def scratch_config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
    monkeypatch.setenv("HOME", str(tmp_path))
    return config_directory


def _entry_fields(**overrides: object) -> dict[str, object]:
    all_fields: dict[str, object] = {
        "id": "3f9a",
        "tool_name": "Bash",
        "rule_label": "Git Destructive",
        "action_summary": "git push -f",
        "sequence": 2,
        "answer": "kept",
    }
    all_fields.update(overrides)
    return all_fields


def test_should_place_the_ledger_under_the_config_directory(scratch_config_directory: Path) -> None:
    assert ledger_files.ledger_directory_for("s-1") == (
        scratch_config_directory / "state" / "auto-mode-refusals" / "s-1"
    )
    assert ledger_files.ledger_directory_for("../x").name == "___x"


def test_should_give_two_edits_of_one_file_two_ids() -> None:
    first_id = ledger_files.entry_id_for("Edit", {"file_path": "a.py", "old_string": "x"})
    second_id = ledger_files.entry_id_for("Edit", {"file_path": "a.py", "old_string": "y"})
    assert first_id != second_id
    assert first_id == ledger_files.entry_id_for("Edit", {"old_string": "x", "file_path": "a.py"})


def test_should_give_a_retry_with_a_new_description_the_same_id() -> None:
    first_id = ledger_files.entry_id_for(
        "Bash", {"command": "python3 -c 1", "description": "Write marker file"}
    )
    retry_id = ledger_files.entry_id_for(
        "Bash", {"command": "python3 -c 1", "description": "Retry writing marker file"}
    )
    other_command_id = ledger_files.entry_id_for(
        "Bash", {"command": "python3 -c 2", "description": "Write marker file"}
    )
    assert first_id == retry_id
    assert first_id != other_command_id


def test_should_parse_an_entry_with_every_field_typed() -> None:
    assert ledger_files.parse_entry(_entry_fields()) == ledger_files.LedgerEntry(
        "3f9a", "Bash", "Git Destructive", "git push -f", 2, "kept"
    )


def test_should_parse_the_stop_gate_counts_and_asked_mark() -> None:
    parsed_entry = ledger_files.parse_entry(
        _entry_fields(question_holds=2, rule_holds=1, question_asked=True)
    )
    assert parsed_entry is not None
    assert (parsed_entry.question_holds, parsed_entry.rule_holds) == (2, 1)
    assert parsed_entry.is_question_asked


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": 7},
        {"sequence": "first"},
        {"sequence": True},
        {"answer": "maybe"},
        {"question_holds": "2"},
        {"rule_holds": None},
        {"question_asked": 1},
    ],
)
def test_should_reject_an_entry_with_a_field_of_the_wrong_type(
    overrides: dict[str, object],
) -> None:
    assert ledger_files.parse_entry(_entry_fields(**overrides)) is None


def test_should_reject_an_entry_without_an_id_or_an_answer_key() -> None:
    entry_fields = _entry_fields()
    del entry_fields["id"]
    assert ledger_files.parse_entry(entry_fields) is None
    assert ledger_files.parse_entry({"question": "Q?"}) is None


def test_should_parse_a_question_record_and_reject_a_bad_offset() -> None:
    record_fields = {
        "record": "question",
        "question": "Q?",
        "entry_ids": ["a", "b"],
        "transcript_offset": 900,
    }
    assert ledger_files.parse_question_record(record_fields) == ledger_files.QuestionRecord(
        "Q?", ("a", "b"), 900
    )
    assert (
        ledger_files.parse_question_record({**record_fields, "transcript_offset": "late"}) is None
    )
    assert ledger_files.parse_question_record({**record_fields, "entry_ids": [1]}) is None
    assert ledger_files.parse_question_record(
        {**record_fields, "tool_name": "Bash"}
    ) == ledger_files.QuestionRecord("Q?", ("a", "b"), 900, "Bash")
    assert ledger_files.parse_question_record({**record_fields, "tool_name": 7}) == (
        ledger_files.QuestionRecord("Q?", ("a", "b"), 900, "")
    )


def test_should_write_and_read_back_one_object(tmp_path: Path) -> None:
    entry_path = ledger_files.entry_file_path(tmp_path / "ledger", "3f9a")
    ledger_files.write_json_object(entry_path, _entry_fields())
    assert entry_path.name == "3f9a.json"
    assert ledger_files.read_json_object(entry_path) == _entry_fields()
    entry_path.write_text("[1, 2]", encoding="utf-8")
    assert ledger_files.read_json_object(entry_path) is None


def test_should_load_only_the_files_that_parse_oldest_first(tmp_path: Path) -> None:
    ledger_files.write_json_object(tmp_path / "late.json", _entry_fields(id="late", sequence=5))
    ledger_files.write_json_object(tmp_path / "early.json", _entry_fields(id="early", sequence=1))
    (tmp_path / "no-id.json").write_text(json.dumps({"answer": None}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert [each.entry_id for each in ledger_files.load_entries(tmp_path)] == ["early", "late"]


def test_should_load_only_the_question_records_that_parse(tmp_path: Path) -> None:
    question_path = ledger_files.question_file_path(tmp_path, "Q?")
    ledger_files.write_json_object(
        question_path,
        {"record": "question", "question": "Q?", "entry_ids": ["a"], "transcript_offset": 3},
    )
    ledger_files.write_json_object(
        ledger_files.question_file_path(tmp_path, "Other?"),
        {"record": "question", "question": "Other?", "entry_ids": "a"},
    )
    assert question_path.name.startswith("question-")
    assert ledger_files.load_question_records(tmp_path) == [
        ledger_files.QuestionRecord("Q?", ("a",), 3)
    ]
