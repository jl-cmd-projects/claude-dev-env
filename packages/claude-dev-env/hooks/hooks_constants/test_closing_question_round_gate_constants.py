import pytest

from hooks_constants.closing_question_round_gate_constants import (
    ALL_REASON_LEADS,
    CLOSING_ROUND_INSTRUCTION,
    DECLARATION_LINE_PATTERN,
    ESCAPED_PRINTABLE_ASCII_PATTERN,
    FILE_NAME_PATTERN,
    FOOTER_HEADING,
    FOOTER_INSTRUCTION,
    PATH_EDGE_CHARACTERS,
    NO_OPEN_ITEMS_DECLARATION,
    OPEN_ITEM_MARKER_PATTERN,
    OUTPUT_WATCHDOG_SECONDS,
    STDIN_WATCHDOG_SECONDS,
)


def test_marker_pattern_should_find_follow_up_and_pending() -> None:
    all_markers = [
        each_match.group(0)
        for each_match in OPEN_ITEM_MARKER_PATTERN.finditer("A follow-up is pending.")
    ]
    assert all_markers == ["follow-up", "pending"]


@pytest.mark.parametrize(
    ("open_line", "marker"),
    [
        ("You may want to decide on the timeout.", "You may want to"),
        ("I didn't test the retry path.", "didn't test"),
        ("I'll do the docs in a separate PR.", "separate PR"),
        ("I was unable to confirm the size.", "unable to confirm"),
        ("The warm-up is not yet implemented.", "not yet implemented"),
        ("This rests on your judgment.", "your judgment"),
    ],
)
def test_marker_pattern_should_find_each_added_wording(open_line: str, marker: str) -> None:
    marker_match = OPEN_ITEM_MARKER_PATTERN.search(open_line)
    assert marker_match is not None
    assert marker_match.group(0) == marker


def test_instructions_should_ask_for_the_footer_and_never_for_the_declaration() -> None:
    assert FOOTER_HEADING in FOOTER_INSTRUCTION
    assert "In progress footer" in CLOSING_ROUND_INSTRUCTION
    assert f"line {NO_OPEN_ITEMS_DECLARATION}" not in CLOSING_ROUND_INSTRUCTION
    assert f"Do not end with the line {NO_OPEN_ITEMS_DECLARATION}" in FOOTER_INSTRUCTION
    assert len(set(ALL_REASON_LEADS)) == 4


def test_footer_instruction_should_hold_no_example_sentence_to_copy() -> None:
    assert "'" not in FOOTER_INSTRUCTION
    assert "I am" not in FOOTER_INSTRUCTION


@pytest.mark.parametrize(
    ("json_text", "is_escaped_printable"),
    [('"\\u0074urnOrigin"', True), ('"\\u007E"', True), ('"\\u001b[0m"', False), ('"\\u00e9"', False)],
)
def test_escaped_printable_ascii_pattern_should_find_only_printable_ascii_escapes(
    json_text: str, is_escaped_printable: bool
) -> None:
    assert bool(ESCAPED_PRINTABLE_ASCII_PATTERN.search(json_text)) is is_escaped_printable


def test_watchdogs_should_end_a_held_stop_inside_the_host_timeout_of_ten_seconds() -> None:
    assert STDIN_WATCHDOG_SECONDS + OUTPUT_WATCHDOG_SECONDS < 10


@pytest.mark.parametrize(
    ("declaration_line", "is_declaration"),
    [
        ("Open items: none.", True),
        ("Open items: none", True),
        ("**Open items: none**", True),
        ("Open items: none..", False),
        ("**Open items: none*", False),
    ],
)
def test_declaration_line_pattern_should_leave_the_final_period_optional(
    declaration_line: str, is_declaration: bool
) -> None:
    assert (DECLARATION_LINE_PATTERN.fullmatch(declaration_line) is not None) is is_declaration


@pytest.mark.parametrize(
    ("segment_text", "is_file_name"),
    [("todo.md", True), ("notes.json", True), ("TODO.Ship", False), ("e.g.pending", False)],
)
def test_file_name_pattern_should_take_a_short_lower_case_extension(
    segment_text: str, is_file_name: bool
) -> None:
    assert (FILE_NAME_PATTERN.fullmatch(segment_text) is not None) is is_file_name


def test_path_edge_characters_should_strip_quotes_and_emphasis_around_a_file_name() -> None:
    for each_wrapped_name in ["**todo.md**", "_todo.md_", "~~todo.md~~", "\u201ctodo.md\u201d", "\u2039todo.md\u203a", "(todo.md)."]:
        assert each_wrapped_name.strip(PATH_EDGE_CHARACTERS) == "todo.md"
