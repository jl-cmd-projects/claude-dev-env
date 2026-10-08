"""Behavior tests for the visual reply rule list."""

import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from visual_reply_rules import (
    abbreviation_violation,
    load_rules,
    mode_enabled,
    replies_sent_this_turn,
    second_reply_violation,
    visual_shown_this_turn,
    visual_violation,
    widget_anchor_violation,
)

SHIPPED_RULES = load_rules()


def prompt_line(text: str) -> str:
    return json.dumps({"type": "user", "message": {"content": text}})


def tool_line(tool_name: str) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": tool_name}]}}
    )


def test_shipped_rule_file_parses_with_a_label_and_reminder_per_rule() -> None:
    rules = load_rules()
    assert rules is not None
    assert {each.key for each in rules.all_rules} >= {"one_item", "no_picture", "abbreviations"}
    assert all(each.label and each.reminder for each in rules.all_rules)


def test_load_rules_returns_none_when_a_needed_rule_is_missing(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"key": "no_picture", "label": "No picture", "reminder": "Draw it."}]}),
        encoding="utf-8",
    )
    assert load_rules(rules_path) is None


def test_mode_is_off_without_a_switch_file(tmp_path: Path) -> None:
    assert mode_enabled(tmp_path) is False


def test_mode_is_on_when_the_switch_file_says_so(tmp_path: Path) -> None:
    (tmp_path / "visual-reply-mode.json").write_text('{"enabled": true}', encoding="utf-8")
    assert mode_enabled(tmp_path) is True


def test_abbreviation_violation_names_the_abbreviation_and_allows_listed_words() -> None:
    assert SHIPPED_RULES is not None
    assert 'Abbreviation "UI"' in str(abbreviation_violation("The UI is done.", SHIPPED_RULES))
    assert abbreviation_violation("OK, I merged it.", SHIPPED_RULES) is None


def test_abbreviation_violation_flags_a_lowercase_abbreviation_and_a_tracker_number() -> None:
    assert SHIPPED_RULES is not None
    assert 'Abbreviation "e.g."' in str(abbreviation_violation("Logs, e.g. the error log.", SHIPPED_RULES))
    assert 'Tracker number "card 12"' in str(abbreviation_violation("See card 12.", SHIPPED_RULES))


def test_widget_anchor_violation_reads_only_widget_calls() -> None:
    anchor_input = {"widget_code": '<a href="https://example.com">page</a>'}
    assert widget_anchor_violation("mcp__hearthbot__post_widget", anchor_input) is not None
    assert widget_anchor_violation("mcp__hearthbot__reply", anchor_input) is None


def test_visual_shown_this_turn_counts_only_calls_after_the_last_prompt() -> None:
    assert visual_shown_this_turn([prompt_line("status"), tool_line("Artifact")])
    assert not visual_shown_this_turn(
        [prompt_line("status"), tool_line("mcp__hearthbot__post_widget"), prompt_line("next")]
    )


def test_visual_violation_reads_the_transcript_file(tmp_path: Path) -> None:
    assert SHIPPED_RULES is not None
    transcript_path = tmp_path / "t.jsonl"
    transcript_path.write_text(prompt_line("status"), encoding="utf-8")
    assert visual_violation(2, str(transcript_path), SHIPPED_RULES) is not None
    assert visual_violation(1, str(transcript_path), SHIPPED_RULES) is None
    assert visual_violation(2, str(tmp_path / "missing.jsonl"), SHIPPED_RULES) is None


def reply_use_line(tool_use_id: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": tool_use_id, "name": "mcp__thread__reply"}]
            },
        }
    )


def result_line(tool_use_id: str, is_error: bool) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error}]
            },
        }
    )


def test_replies_sent_this_turn_counts_delivered_replies_after_the_last_prompt() -> None:
    all_lines = [
        prompt_line("earlier"),
        reply_use_line("a"),
        result_line("a", False),
        prompt_line("status"),
        reply_use_line("b"),
        result_line("b", True),
        reply_use_line("c"),
        result_line("c", False),
        reply_use_line("d"),
    ]
    assert replies_sent_this_turn(all_lines) == 1


def test_second_reply_violation_denies_only_after_a_delivered_reply(tmp_path: Path) -> None:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join([prompt_line("status"), reply_use_line("a"), result_line("a", True)]),
        encoding="utf-8",
    )
    assert second_reply_violation(str(transcript_path), SHIPPED_RULES) is None
    transcript_path.write_text(
        "\n".join([prompt_line("status"), reply_use_line("a"), result_line("a", False)]),
        encoding="utf-8",
    )
    assert second_reply_violation(str(transcript_path), SHIPPED_RULES) is not None
    assert second_reply_violation(str(tmp_path / "missing.jsonl"), SHIPPED_RULES) is None
