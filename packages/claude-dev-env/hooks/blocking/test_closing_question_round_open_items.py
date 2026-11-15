import pytest

from closing_question_round_open_items import (
    declares_no_open_items,
    indented_code_masked,
    marked_open_lines,
)
from hooks_constants.closing_question_round_gate_constants import (
    MARKER_SCAN_WINDOW_CHARACTERS,
    MAXIMUM_SCANNED_BYTES,
    MAXIMUM_SCANNED_TEXT_BYTES,
)

NO_DEADLINE = float("inf")


def test_marked_open_lines_returns_each_marked_line_once_in_order() -> None:
    all_assistant_texts = [
        "The flag is in place.\nThe retry path is untested.\n\n- The cleanup is parked.",
        "The cleanup is out of\nscope for now.\nBoth tests pass.",
        "The retry path is untested.",
    ]
    assert marked_open_lines(all_assistant_texts, NO_DEADLINE) == [
        "The retry path is untested.",
        "- The cleanup is parked.",
        "The cleanup is out of scope for now.",
    ]


@pytest.mark.parametrize(
    "negated_line",
    [
        "No follow-up is needed.",
        "No open questions remain.",
        "Nothing deferred, except the backoff setting.",
        "Nothing is deferred.",
    ],
)
def test_marked_open_lines_should_keep_a_negated_marker(negated_line: str) -> None:
    assert marked_open_lines([negated_line], NO_DEADLINE) == [negated_line]


def test_marked_open_lines_should_find_a_marker_that_spans_a_scan_window_edge() -> None:
    straddling_text = "w" * (MARKER_SCAN_WINDOW_CHARACTERS - 4) + " untested\nBoth tests pass."
    assert marked_open_lines([straddling_text], NO_DEADLINE) == [straddling_text.split("\n")[0]]


def test_marked_open_lines_should_skip_a_word_cut_at_a_scan_window_edge() -> None:
    cut_text = "w" * (MARKER_SCAN_WINDOW_CHARACTERS + 128 - 6) + " deference is kept."
    assert marked_open_lines([cut_text], NO_DEADLINE) == []


def test_marked_open_lines_should_skip_a_text_over_sixteen_mebibytes() -> None:
    oversized_text = "The retry path is untested. " + "x" * MAXIMUM_SCANNED_BYTES
    assert marked_open_lines([oversized_text, "The cleanup is parked."], NO_DEADLINE) == [
        "The cleanup is parked."
    ]


def test_marked_open_lines_should_raise_once_the_deadline_passes() -> None:
    with pytest.raises(TimeoutError):
        marked_open_lines(["The cleanup is parked."], 0.0)


@pytest.mark.parametrize(
    ("reply_text", "masked_text"),
    [
        ("Run this:\n\n    queue --deferred\n\nDone.", "Run this:\n\n\n\nDone."),
        ("\tqueue --deferred\nDone.", "\nDone."),
        ("- Item\n\n    The retry is untested.", "- Item\n\n    The retry is untested."),
        ("One line\n    more deferred text", "One line\n    more deferred text"),
    ],
)
def test_indented_code_masked_blanks_only_an_indented_code_block(
    reply_text: str, masked_text: str
) -> None:
    assert indented_code_masked(reply_text, NO_DEADLINE) == masked_text


@pytest.mark.parametrize(
    ("closing_reply", "is_declaration"),
    [
        ("Both tests pass.\n\nOpen items: none.", True),
        ("Both tests pass.\n\n**Open items: none.**", True),
        ("Open items: none.\n\nBoth tests pass.", False),
        ("`Open items: none.`", False),
        ("- Open items: none.", False),
        ("Open items: none", False),
        ("", False),
        ("Open items: none." + "x" * MAXIMUM_SCANNED_BYTES + "\nOpen items: none.", False),
    ],
)
def test_declares_no_open_items_reads_the_last_prose_line(
    closing_reply: str, is_declaration: bool
) -> None:
    assert declares_no_open_items(closing_reply, NO_DEADLINE) is is_declaration


@pytest.mark.parametrize("gap", [" " * 300, "\n" + " " * 300])
def test_marked_open_lines_should_find_a_marker_whose_long_gap_straddles_a_window_edge(
    gap: str,
) -> None:
    marker_text = f"out{gap}of scope here."
    leading_text = "a" * (MARKER_SCAN_WINDOW_CHARACTERS - 150) + " "
    all_lines = marked_open_lines([leading_text + marker_text], NO_DEADLINE)
    assert len(all_lines) == 1
    assert all_lines[0].endswith("of scope here.")


def test_marked_open_lines_should_skip_a_text_over_the_text_cap() -> None:
    oversized_text = "The retry path is untested.\n" + "a" * (MAXIMUM_SCANNED_TEXT_BYTES + 1)
    assert marked_open_lines([oversized_text], NO_DEADLINE) == []


@pytest.mark.parametrize(
    "emphasized_line",
    ["The retry is _untested_.", "The cleanup is __deferred__.", "The flag is _parked_ for now."],
)
def test_marked_open_lines_should_read_a_marker_inside_underscore_emphasis(
    emphasized_line: str,
) -> None:
    assert marked_open_lines([emphasized_line], NO_DEADLINE) == [emphasized_line]


def test_marked_open_lines_should_not_read_a_marker_inside_a_snake_case_name() -> None:
    assert marked_open_lines(["The retry_untested_flag is set."], NO_DEADLINE) == []


def test_marked_open_lines_should_find_a_window_edge_marker_followed_only_by_hyphens() -> None:
    leading_text = "x" * (MARKER_SCAN_WINDOW_CHARACTERS - 10)
    all_lines = marked_open_lines([leading_text + " out of" + " " * 20 + "scope---"], NO_DEADLINE)
    assert len(all_lines) == 1


@pytest.mark.parametrize("list_marker", ["1.", "-"])
def test_marked_open_lines_should_read_an_indented_paragraph_inside_a_wrapped_list_item(
    list_marker: str,
) -> None:
    reply_text = (
        f"{list_marker} Retry path\n   covers the timeout case.\n\n"
        "    I deferred the backoff setting.\n\nOpen items: none."
    )
    assert marked_open_lines([reply_text], NO_DEADLINE) == ["I deferred the backoff setting."]


def test_indented_code_masked_blanks_an_indented_block_after_a_list_ends() -> None:
    reply_text = "- Retry path\n\nThe flag is set.\n\n    deferred = True"
    assert indented_code_masked(reply_text, NO_DEADLINE).split("\n")[-1] == ""


@pytest.mark.parametrize("tail", ["-", "------", "\n---", ""])
def test_marked_open_lines_should_find_a_marker_split_by_a_whitespace_run_past_a_window(
    tail: str,
) -> None:
    marker_text = "The cleanup is out" + " " * 1_100_000 + "of scope" + tail
    all_lines = marked_open_lines([marker_text], NO_DEADLINE)
    assert len(all_lines) == 1
    assert all_lines[0].startswith("The cleanup is out")


def test_marked_open_lines_should_quote_the_lines_of_a_marker_beside_long_space_runs() -> None:
    reply_text = "The   flag  is set.\nThe   cleanup  is out  of\nscope   now."
    assert marked_open_lines([reply_text], NO_DEADLINE) == [
        "The   cleanup  is out  of scope   now."
    ]
