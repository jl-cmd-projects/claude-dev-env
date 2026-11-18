import json
from pathlib import Path

from repeated_lines import counted_lines, has_footer, repeat_report, report_rows, transcript_replies

FOOTER_ITEM = "I am shipping pull request 8590 once its automated tests pass."
FOOTER = f"In progress:\n- {FOOTER_ITEM}\n- I am shipping pull request 8693 once 8590 is in."


def test_should_cut_list_markers_fold_spaces_and_drop_short_lines() -> None:
    assert counted_lines(f"Done.\n\n{FOOTER}") == [
        FOOTER_ITEM,
        "I am shipping pull request 8693 once 8590 is in.",
    ]
    assert counted_lines("1.   Spaces   are  folded in this line.") == ["Spaces are folded in this line."]


def test_should_count_each_line_an_earlier_reply_already_sent() -> None:
    reworded_footer = FOOTER.replace("once 8590 is in", "after 8590 merges")
    report = repeat_report([f"Done.\n\n{FOOTER}", f"Nothing is new here.\n\n{FOOTER}", reworded_footer])
    assert report.reply_count == 3
    assert report.footer_count == 3
    assert report.repeated_line_count == 3
    assert report.all_top_lines[0] == (FOOTER_ITEM, 3)


def test_should_find_no_repeat_in_replies_that_each_say_something_new() -> None:
    report = repeat_report([f"Done.\n\n{FOOTER}", "The tests on pull request 8590 passed."])
    assert report.repeated_line_count == 0
    assert report.footer_count == 1
    assert report.all_top_lines == []


def test_should_read_a_footer_heading_only_on_a_line_of_its_own() -> None:
    assert has_footer("Done.\n\n**In progress:**\n- I am shipping it.")
    assert not has_footer("The In progress: list is below.")


def test_should_read_each_assistant_text_block_of_a_transcript(tmp_path: Path) -> None:
    all_records = [
        {"type": "user", "message": {"role": "user", "content": "Ship it."}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": FOOTER}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "A subagent note."}]}},
    ]
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join([*map(json.dumps, all_records), "not json"]), encoding="utf-8")
    assert transcript_replies(transcript_path) == [FOOTER]


def test_should_print_the_summary_then_each_line_sent_more_than_once() -> None:
    all_rows = report_rows(repeat_report([FOOTER, FOOTER]))
    assert all_rows[0] == "replies 2, counted lines 4, footer copies 2, repeated lines 2"
    assert all_rows[1] == f"  x2 {FOOTER_ITEM}"
