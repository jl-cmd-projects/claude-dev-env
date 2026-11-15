import pytest

from hooks_constants.closing_question_round_gate_constants import (
    ALL_REASON_LEADS,
    CLOSING_ROUND_INSTRUCTION,
    ESCAPED_PRINTABLE_ASCII_PATTERN,
    NO_OPEN_ITEMS_DECLARATION,
    OPEN_ITEM_MARKER_PATTERN,
    OUTPUT_WATCHDOG_SECONDS,
    STDIN_WATCHDOG_SECONDS,
    WORK_INSTRUCTION,
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


def test_declaration_should_carry_no_marker_and_end_both_instructions() -> None:
    assert OPEN_ITEM_MARKER_PATTERN.search(NO_OPEN_ITEMS_DECLARATION) is None
    assert WORK_INSTRUCTION.endswith(NO_OPEN_ITEMS_DECLARATION)
    assert NO_OPEN_ITEMS_DECLARATION in CLOSING_ROUND_INSTRUCTION
    assert len(set(ALL_REASON_LEADS)) == 2


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
