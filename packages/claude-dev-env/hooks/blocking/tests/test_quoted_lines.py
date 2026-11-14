"""Behavioral tests for cutting shell text into the logical lines bash reads.

a ; b<line break>c                -> two lines
bash -c "a<line break>b"          -> one line, the line break kept in the word
echo $'it\\'s'                     -> echo 'it'\\''s'
echo "open                        -> None
"""

from __future__ import annotations

import shlex

import pytest

from blocking.merge_review_gate_parts.quoted_lines import quote_aware_lines


def _words(text: str) -> list[list[str]]:
    all_lines = quote_aware_lines(text)
    assert all_lines is not None
    return [shlex.split(each_line) for each_line in all_lines]


def test_should_cut_at_a_line_break_outside_quotes() -> None:
    assert quote_aware_lines("a ; b\nc\r\nd") == ["a ; b", "c", "d"]


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ('bash -c "true\ngh pr create"', "true\ngh pr create"),
        ("bash -c 'true\ngh pr create'", "true\ngh pr create"),
        ("bash -c $'true\\ngh pr create'", "true\ngh pr create"),
    ],
)
def test_should_keep_a_quoted_line_break_inside_its_word(text: str, word: str) -> None:
    assert _words(text) == [["bash", "-c", word]]


@pytest.mark.parametrize(
    ("text", "body"),
    [
        ("x --body $'it\\'s' ; y", "it's"),
        ("x --body $'\\'' ; y", "'"),
        ("x --body $'a\\\\b\\\"c' ; y", 'a\\b"c'),
    ],
)
def test_should_read_an_ansi_c_word_as_bash_does(text: str, body: str) -> None:
    assert _words(text) == [["x", "--body", body, ";", "y"]]


def test_should_keep_a_quote_inside_a_double_quoted_substitution_in_its_word() -> None:
    assert _words('x --body "$(echo \'"\' \\\\)" ; y') == [
        ["x", "--body", "$(echo '\"' \\\\)", ";", "y"]
    ]


def test_should_join_a_line_break_inside_a_group_or_substitution_with_a_separator() -> None:
    assert quote_aware_lines("(cd a\ngh pr create)\nx=$(true\nls)") == [
        "(cd a;gh pr create)",
        "x=$(true;ls)",
    ]


def test_should_drop_comments_and_heredoc_bodies() -> None:
    text = "cat <<'EOF' # note\nit's \"open\nEOF\necho a#b # tail\nls"
    assert quote_aware_lines(text) == ["cat <<'EOF' ", "echo a#b ", "ls"]


def test_should_skip_no_lines_after_a_quoted_heredoc_word() -> None:
    assert quote_aware_lines('x --body "a <<EOF"\nls\nEOF') == ['x --body "a <<EOF"', "ls", "EOF"]


def test_should_join_a_line_continuation() -> None:
    assert quote_aware_lines('a \\\nb "c\\\nd"') == ['a b "cd"']


@pytest.mark.parametrize("text", ['echo "open', "echo 'open", "echo $'open", "x=$(ls", "(ls"])
def test_should_return_none_for_text_left_open(text: str) -> None:
    assert quote_aware_lines(text) is None
