"""Behavior tests for the visual reply rule list."""

import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.visual_reply_rules_constants import RULES_FILE_PATH
from visual_reply_rules import (
    abbreviation_violation,
    attaches_picture,
    load_rules,
    mode_enabled,
    replies_sent_this_turn,
    reports_results,
    results_picture_violation,
    second_reply_violation,
    successful_result_text,
    visual_shown_this_turn,
    visual_violation,
    widget_anchor_violation,
    widget_flowchart_advice,
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


def test_abbreviation_violation_names_every_abbreviation_and_tracker_number_on_its_own_line() -> None:
    assert SHIPPED_RULES is not None
    violation = str(abbreviation_violation("The UI and the API, e.g. card 12 and card 13.", SHIPPED_RULES))
    all_lines = violation.splitlines()
    assert len(all_lines) == 5
    assert 'Abbreviation "UI"' in all_lines[0]
    assert 'Abbreviation "API"' in all_lines[1]
    assert 'Abbreviation "e.g."' in all_lines[2]
    assert 'Tracker number "card 12"' in all_lines[3]
    assert 'Tracker number "card 13"' in all_lines[4]


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


def widget_use_line(tool_use_id: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": tool_use_id, "name": "mcp__hearthbot__post_widget"}
                ]
            },
        }
    )


def test_visual_shown_this_turn_skips_a_widget_that_came_back_with_an_error() -> None:
    assert not visual_shown_this_turn(
        [prompt_line("status"), widget_use_line("w"), result_line("w", True)]
    )
    assert visual_shown_this_turn([prompt_line("status"), widget_use_line("w"), result_line("w", False)])
    assert visual_shown_this_turn([prompt_line("status"), widget_use_line("w")])


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


FLOWCHART_CODE = (
    '<svg><path d="M0 20L40 0L80 20L40 40Z"/>'
    '<path d="M80 20H120" marker-end="url(#a)"/></svg>'
)


def test_widget_flowchart_advice_should_pass_an_svg_with_a_diamond_and_arrows() -> None:
    rules = load_rules()
    assert rules is not None
    nested_input = {"input": {"widget_code": FLOWCHART_CODE}}
    assert widget_flowchart_advice("mcp__hearthbot__post_widget", nested_input, rules) is None


def test_widget_flowchart_advice_should_advise_on_cards_and_shapes_without_a_decision() -> None:
    rules = load_rules()
    assert rules is not None
    card_input = {"widget_code": "<div class='card'>Merged</div>"}
    no_diamond_input = {"widget_code": '<svg><path marker-end="url(#a)"/></svg>'}
    arrowhead_only_input = {
        "widget_code": '<svg><marker id="a"><polygon points="0 0,9 5,0 9"/></marker>'
        '<rect/><path marker-end="url(#a)"/></svg>'
    }
    for each_input in (card_input, no_diamond_input, arrowhead_only_input):
        reason = widget_flowchart_advice("mcp__hearthbot__post_widget", each_input, rules)
        assert reason is not None and "diamond" in reason
    assert widget_flowchart_advice("mcp__hearthbot__reply", card_input, rules) is None


def test_widget_flowchart_advice_should_stay_quiet_when_the_rule_list_has_no_flowchart_rule(
    tmp_path: Path,
) -> None:
    shipped_document = json.loads(RULES_FILE_PATH.read_text(encoding="utf-8"))
    shipped_document["rules"] = [
        each for each in shipped_document["rules"] if each["key"] != "not_flowchart"
    ]
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(shipped_document), encoding="utf-8")
    rules = load_rules(rules_path)
    assert rules is not None
    card_input = {"widget_code": "<div class='card'>Merged</div>"}
    assert widget_flowchart_advice("mcp__hearthbot__post_widget", card_input, rules) is None


def test_successful_result_text_joins_only_results_without_an_error(tmp_path: Path) -> None:
    all_entries = [
        {"type": "user", "message": {"content": "run 111 from the prompt"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "run 222 ok"}]}},
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": [{"type": "text", "text": "run 333 ok"}]},
                    {"type": "tool_result", "is_error": True, "content": "run 444 failed"},
                ]
            },
        },
    ]
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text("\n".join(json.dumps(each) for each in all_entries), encoding="utf-8")
    assert successful_result_text(str(transcript_path)) == "run 222 ok\nrun 333 ok"
    assert successful_result_text(str(tmp_path / "missing.jsonl")) is None


def test_reports_results_flags_a_markdown_table_and_three_figures() -> None:
    assert reports_results("| Check | Result |\n|---|---|\n| Unit tests | passed |")
    assert reports_results("The run shows 65 passed, 0 failed, and 3 skipped.")
    assert not reports_results("The run shows 65 passed and 3 skipped.")


def test_reports_results_counts_a_multiplier_such_as_2_5x_as_a_figure() -> None:
    assert reports_results("Latency fell 2.5x and throughput rose 3x and errors fell 4x.")


def test_reports_results_counts_no_figure_in_a_long_run_or_job_identifier() -> None:
    assert not reports_results("Run 24011273, job 24011274 and check 24011275 are green.")


def test_reports_results_counts_a_negative_figure_as_a_figure() -> None:
    assert reports_results("Deltas were -2, -5 and -7 this week.")


def test_reports_results_counts_no_figure_in_a_date_or_a_pull_request_number() -> None:
    assert not reports_results("Shipped on 2026-10-29 in #2224.")


def test_reports_results_counts_no_figure_in_a_clock_time_or_a_list_number() -> None:
    assert not reports_results("The run started at 10:30 and ended at 11:45.")
    assert not reports_results("1. Checked the hook.\n2. Checked the rule.\n3. Checked the test.")


def test_reports_results_flags_a_markdown_table_written_without_leading_pipes() -> None:
    assert reports_results("Check | Result\n--- | ---\nUnit tests | passed")


def test_attaches_picture_ignores_a_picture_shown_only_inside_a_code_fence() -> None:
    assert not attaches_picture("Example:\n```\n![Chart](chart.png)\n```\nDone.", {})


def test_attaches_picture_accepts_a_markdown_picture_with_a_title_or_a_query_string() -> None:
    assert attaches_picture('Results.\n\n![Chart](chart.png "Results")', {})
    assert attaches_picture("Results.\n\n![Chart](https://x.example/c.png?w=2)", {})


def test_attaches_picture_accepts_an_image_file_or_a_markdown_picture_only() -> None:
    assert attaches_picture("Results.", {"attached_outputs": [{"kind": "file", "ref": "/mnt/chart.svg"}]})
    assert attaches_picture("![Chart](chart.png)", {})
    assert not attaches_picture("Results.", {"attached_outputs": [{"kind": "file", "ref": "results.md"}]})
    assert not attaches_picture("Results.", {"attached_outputs": [{"kind": "link", "ref": "https://x.example/c.png"}]})
    assert not attaches_picture("Results.", {})


def test_results_picture_violation_names_the_picture_rule_and_allows_an_attached_chart() -> None:
    assert SHIPPED_RULES is not None
    results_text = "The run shows 65 passed, 0 failed, and 3 skipped."
    violation = results_picture_violation(results_text, results_text, {}, SHIPPED_RULES)
    assert violation is not None
    assert "reports results with no picture attached" in violation
    chart_input = {"attached_outputs": [{"kind": "file", "ref": "chart.svg"}]}
    assert results_picture_violation(results_text, results_text, chart_input, SHIPPED_RULES) is None
    assert results_picture_violation(results_text, results_text, {}, None) is None
