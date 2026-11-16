"""Behavior tests for the auto mode refusal ledger."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import auto_mode_refusal_ledger as ledger


@pytest.fixture(autouse=True)
def scratch_config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK", raising=False)
    return config_directory


def _add(ledger_directory: Path, command: str, rule_label: str = "Git Destructive") -> str:
    tool_input = {"command": command}
    entry_id = ledger.entry_id_for("Bash", tool_input)
    ledger.add_entry(
        ledger_directory,
        {
            "id": entry_id,
            "tool_name": "Bash",
            "tool_input": tool_input,
            "rule_label": rule_label,
            "action_summary": command,
        },
    )
    return entry_id


def _append_ask(transcript_path: Path, question: str, answer: str, tool_use_id: str) -> None:
    call_record = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "AskUserQuestion",
                    "input": {"questions": [{"question": question}]},
                }
            ]
        },
    }
    result_record = {
        "type": "user",
        "toolUseResult": {"questions": [{"question": question}], "answers": {question: answer}},
        "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id}]},
    }
    with transcript_path.open("a", encoding="utf-8") as transcript_file:
        transcript_file.write(json.dumps(call_record) + "\n" + json.dumps(result_record) + "\n")


def _answers(ledger_directory: Path) -> list[object]:
    return [each_entry.answer for each_entry in ledger.load_entries(ledger_directory)]


def test_should_turn_the_flow_on_only_for_an_existing_playbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ledger.playbook_path_from_environment() is None
    monkeypatch.setenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK", str(tmp_path / "missing.md"))
    assert ledger.playbook_path_from_environment() is None
    playbook_path = tmp_path / "auto-mode-rule.md"
    playbook_path.write_text("# Playbook\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK", str(playbook_path))
    assert ledger.playbook_path_from_environment() == playbook_path


def _rule_repository(tmp_path: Path) -> Path:
    repository_root = tmp_path / "agent-channels"
    (repository_root / ".git").mkdir(parents=True)
    (repository_root / "setup").mkdir()
    (repository_root / "setup" / "add_auto_mode_rule.py").write_text("", encoding="utf-8")
    return repository_root


def test_should_find_the_rule_repository_two_folders_above_the_playbook(tmp_path: Path) -> None:
    _rule_repository(tmp_path)
    playbook_path = tmp_path / "agent-channels" / "docs" / "auto-mode-rule.md"
    assert ledger.rule_repository_root(playbook_path) == tmp_path.resolve() / "agent-channels"


@pytest.mark.parametrize("missing_marker", [".git", "setup/add_auto_mode_rule.py"])
def test_should_find_no_rule_repository_without_git_and_the_rule_tool(
    tmp_path: Path, missing_marker: str
) -> None:
    repository_root = _rule_repository(tmp_path)
    marker_path = repository_root / missing_marker
    if marker_path.is_dir():
        marker_path.rmdir()
    else:
        marker_path.unlink()
    playbook_path = repository_root / "docs" / "auto-mode-rule.md"
    assert ledger.rule_repository_root(playbook_path) is None


@pytest.mark.parametrize("playbook_text", ["/auto-mode-rule.md", "/docs/auto-mode-rule.md"])
def test_should_find_no_rule_repository_for_a_playbook_at_or_one_below_the_filesystem_root(
    playbook_text: str,
) -> None:
    assert ledger.rule_repository_root(Path(playbook_text)) is None


def _refused_step(command: str, rule_label: str | None, **overrides: object) -> ledger.RefusedStep:
    all_fields: dict[str, object] = {
        "session_id": "s1",
        "transcript_path": None,
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "working_folder": None,
        "rule_label": rule_label,
        "reason": f"[{rule_label}] refused",
        "action_summary": command,
    }
    all_fields.update(overrides)
    return ledger.RefusedStep(**all_fields)


def test_should_record_a_labelled_refusal_once_and_return_its_question(tmp_path: Path) -> None:
    repository_root = tmp_path / "agent-channels"
    expected_question = ledger.question_text_for("Bash", "Git Destructive", 1)
    for _ in range(2):
        question = ledger.record_refusal(
            _refused_step("git push -f", "Git Destructive"), repository_root
        )
        assert question == expected_question
    assert _answers(ledger.ledger_directory_for("s1")) == [None]


@pytest.mark.parametrize(
    ("command", "rule_label"),
    [
        ("git push -f", None),
        ("python3 setup/add_auto_mode_rule.py add --rule-file r.txt", "Destructive"),
    ],
)
def test_should_record_nothing_for_prose_or_a_rule_flow_step(
    tmp_path: Path, command: str, rule_label: str | None
) -> None:
    repository_root = _rule_repository(tmp_path)
    refused_step = _refused_step(command, rule_label, working_folder=str(repository_root))
    assert ledger.record_refusal(refused_step, repository_root) is None
    assert ledger.load_entries(ledger.ledger_directory_for("s1")) == []


def test_should_record_the_rule_tool_run_from_an_unknown_folder(tmp_path: Path) -> None:
    repository_root = _rule_repository(tmp_path)
    refused_step = _refused_step(
        "python3 setup/add_auto_mode_rule.py add --rule-file r.txt", "Destructive"
    )
    assert ledger.record_refusal(refused_step, repository_root) is not None
    assert len(ledger.load_entries(ledger.ledger_directory_for("s1"))) == 1


def test_should_word_the_question_for_one_step_and_for_several() -> None:
    assert ledger.question_text_for("Bash", "Git Destructive", 1) == (
        "Auto mode refused 1 Bash step under the Git Destructive rule. "
        "Should auto mode have refused it?"
    )
    assert ledger.question_text_for("Bash", "Git Destructive", 3) == (
        "Auto mode refused 3 Bash steps under the Git Destructive rule. "
        "Should auto mode have refused them?"
    )


def test_should_add_one_entry_per_id_in_refusal_order(tmp_path: Path) -> None:
    ledger_directory = tmp_path / "ledger"
    first_id = _add(ledger_directory, "git push -f")
    assert _add(ledger_directory, "git push -f") == first_id
    second_id = _add(ledger_directory, "git reset --hard")
    all_entries = ledger.load_entries(ledger_directory)
    assert [each.entry_id for each in all_entries] == [first_id, second_id]
    assert [each.sequence for each in all_entries] == [1, 2]
    assert _answers(ledger_directory) == [None, None]


def test_should_report_whether_add_entry_wrote_a_file(tmp_path: Path) -> None:
    fields = {"id": "abc", "tool_name": "Bash", "rule_label": "Git"}
    assert ledger.add_entry(tmp_path, fields) is True
    assert ledger.add_entry(tmp_path, fields) is False


def test_should_group_by_tool_and_exact_label_and_cap_at_five(tmp_path: Path) -> None:
    for each_index in range(7):
        _add(tmp_path, f"git push -f origin b{each_index}")
    _add(tmp_path, "git commit --amend", rule_label="Git")
    all_groups = ledger.question_groups(ledger.load_entries(tmp_path))
    assert [each.question for each in all_groups] == [
        ledger.question_text_for("Bash", "Git Destructive", 5),
        ledger.question_text_for("Bash", "Git", 1),
    ]
    assert all_groups[0].all_action_summaries[0] == "git push -f origin b0"


def test_should_keep_a_record_offset_until_its_ids_change(tmp_path: Path) -> None:
    ledger_directory = tmp_path / "ledger"
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text("{}\n", encoding="utf-8")
    _add(ledger_directory, "git push -f")
    ledger.write_question_records(
        ledger_directory,
        ledger.question_groups(ledger.load_entries(ledger_directory)),
        transcript_path,
    )
    transcript_path.write_text("{}\n{}\n{}\n", encoding="utf-8")
    ledger.write_question_records(
        ledger_directory,
        ledger.question_groups(ledger.load_entries(ledger_directory)),
        transcript_path,
    )
    all_records = [
        json.loads(each_path.read_text(encoding="utf-8"))
        for each_path in ledger_directory.glob("question-*.json")
    ]
    assert len(all_records) == 1
    assert "answer" not in all_records[0]
    assert all_records[0]["transcript_offset"] == 3
    assert all_records[0]["question"] == ledger.question_text_for("Bash", "Git Destructive", 1)


def test_should_keep_an_old_answer_off_a_step_that_reuses_its_question(tmp_path: Path) -> None:
    ledger_directory = tmp_path / "ledger"
    transcript_path = tmp_path / "transcript.jsonl"
    question = ledger.question_text_for("Bash", "Git Destructive", 1)

    def refuse_and_record(command: str) -> None:
        _add(ledger_directory, command)
        ledger.apply_transcript_answers(ledger_directory, transcript_path)
        ledger.write_question_records(
            ledger_directory,
            ledger.question_groups(ledger.load_entries(ledger_directory)),
            transcript_path,
        )

    refuse_and_record("git push -f")
    _append_ask(transcript_path, question, "Keep refusing", "toolu_first")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    refuse_and_record("git reset --hard")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == ["kept", None]
    _append_ask(transcript_path, question, "Allow it", "toolu_second")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == ["kept", "allowed"]


def test_should_set_answers_only_from_asks_after_the_record(tmp_path: Path) -> None:
    ledger_directory = tmp_path / "ledger"
    transcript_path = tmp_path / "transcript.jsonl"
    question = ledger.question_text_for("Bash", "Git Destructive", 1)
    _append_ask(transcript_path, question, "Keep refusing", "toolu_early")
    _add(ledger_directory, "git push -f")
    ledger.write_question_records(
        ledger_directory,
        ledger.question_groups(ledger.load_entries(ledger_directory)),
        transcript_path,
    )
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == [None]
    _append_ask(transcript_path, question.lower(), "Allow it", "toolu_other_text")
    _append_ask(transcript_path, question, "allow it", "toolu_other_answer")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == [None]
    _append_ask(transcript_path, question, "Allow it (Recommended)", "toolu_late")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == ["allowed"]


def _write_records(ledger_directory: Path, transcript_path: Path) -> None:
    ledger.write_question_records(
        ledger_directory,
        ledger.question_groups(ledger.load_entries(ledger_directory)),
        transcript_path,
    )


def test_should_take_a_card_text_answer_only_when_one_record_of_the_tool_could_own_it(
    tmp_path: Path,
) -> None:
    ledger_directory = tmp_path / "ledger"
    transcript_path = tmp_path / "transcript.jsonl"
    card_question = "Should auto mode have refused this Bash step?"
    _add(ledger_directory, "git push -f")
    _write_records(ledger_directory, transcript_path)
    _append_ask(transcript_path, card_question, "Allow it", "toolu_card_one")
    ledger.apply_transcript_answers(ledger_directory, transcript_path)
    assert _answers(ledger_directory) == ["allowed"]
    other_directory = tmp_path / "other-ledger"
    other_transcript_path = tmp_path / "other-transcript.jsonl"
    _add(other_directory, "git push -f")
    _add(other_directory, "rm -rf build", rule_label="Irreversible Local Destruction")
    _write_records(other_directory, other_transcript_path)
    _append_ask(other_transcript_path, card_question, "Allow it", "toolu_card_two")
    ledger.apply_transcript_answers(other_directory, other_transcript_path)
    assert _answers(other_directory) == [None, None]


def test_should_apply_answers_from_asks_already_read(tmp_path: Path) -> None:
    ledger_directory = tmp_path / "ledger"
    transcript_path = tmp_path / "transcript.jsonl"
    question = ledger.question_text_for("Bash", "Git Destructive", 1)
    _add(ledger_directory, "git push -f")
    _write_records(ledger_directory, transcript_path)
    _append_ask(transcript_path, question, "Keep refusing", "toolu_kept")
    ledger.apply_asked_answers(ledger_directory, ledger.read_asked_questions(transcript_path))
    assert _answers(ledger_directory) == ["kept"]


def test_should_merge_fields_into_entries_and_keep_their_other_fields(tmp_path: Path) -> None:
    first_id = _add(tmp_path, "git push -f")
    second_id = _add(tmp_path, "git reset --hard")
    ledger.merge_entry_fields(tmp_path, {first_id: {"question_holds": 1}, "missing": {"x": 1}})
    first_entry, second_entry = ledger.load_entries(tmp_path)
    assert (first_entry.question_holds, first_entry.action_summary) == (1, "git push -f")
    assert second_entry.question_holds == 0
    assert second_entry.entry_id == second_id
    assert not (tmp_path / "missing.json").exists()


_PARALLEL_REFUSAL_SCRIPT = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import auto_mode_refusal_ledger as ledger
ledger.record_refusal(
    ledger.RefusedStep(
        session_id="s1",
        transcript_path=None,
        tool_name="Bash",
        tool_input={"command": sys.argv[2]},
        working_folder=None,
        rule_label="Git Destructive",
        reason="[Git Destructive] force push",
        action_summary=sys.argv[2],
    ),
    Path(sys.argv[3]),
)
"""


def test_should_give_parallel_refusals_distinct_sequences_and_one_record_with_every_id(
    tmp_path: Path, scratch_config_directory: Path
) -> None:
    repository_root = _rule_repository(tmp_path)
    hooks_folder = str(Path(ledger.__file__).resolve().parent)
    all_commands = [f"git push -f origin claude/x{each_index}" for each_index in range(8)]
    all_processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _PARALLEL_REFUSAL_SCRIPT,
                hooks_folder,
                each_command,
                str(repository_root),
            ]
        )
        for each_command in all_commands
    ]
    assert [each.wait() for each in all_processes] == [0] * 8
    ledger_directory = ledger.ledger_directory_for("s1")
    all_entries = ledger.load_entries(ledger_directory)
    assert sorted(each.sequence for each in all_entries) == list(range(1, 9))
    all_records = ledger.load_question_records(ledger_directory)
    five_oldest_ids = tuple(
        each.entry_id for each in sorted(all_entries, key=lambda each: each.sequence)[:5]
    )
    five_step_question = ledger.question_text_for("Bash", "Git Destructive", 5)
    assert [
        each.all_entry_ids for each in all_records if each.question == five_step_question
    ] == [five_oldest_ids]


def test_should_clear_a_stale_ledger_lock_after_the_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ledger, "LEDGER_LOCK_WAIT_SECONDS", 0.05)
    ledger_directory = tmp_path / "ledger"
    ledger_directory.mkdir()
    stale_lock_path = ledger_directory / ".ledger.lock"
    stale_lock_path.write_text("", encoding="utf-8")
    with ledger.ledger_lock(ledger_directory):
        _add(ledger_directory, "git push -f")
    assert not stale_lock_path.exists()
    assert _answers(ledger_directory) == [None]
    with ledger.ledger_lock(ledger_directory):
        assert stale_lock_path.exists()
    assert not stale_lock_path.exists()
