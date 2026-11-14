"""Cut shell text into the logical lines bash reads, with each quoted region kept whole.

::

    gh pr create --body $'it\\'s' ; gh pr create  -> one line, $'it\\'s' as 'it'\\''s'
    bash -c "true<line break>gh pr create"       -> one line; the line break stays in the word
    gh pr create --body "$(echo '"')"            -> one line; the inner quote is escaped
    echo 'open                                   -> None

A line break ends a logical line only outside every quote, subshell and
substitution. Inside a subshell or a substitution outside quotes it becomes
``;``. A ``$'...'`` word becomes a single-quoted word. An escaped
``\\$(`` outside quotes keeps its ``(`` in the word. Inside a substitution
in a double-quoted word, each quote and backslash gets a backslash. So a POSIX
``shlex`` split of each line gives the words bash gives. Comments and heredoc
bodies are dropped.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_ANSI_C_ESCAPES,
    ANSI_C_QUOTE_OPENER,
    CARRIAGE_RETURN,
    CARRIAGE_RETURN_LINE_BREAK,
    COMMENT_START_CHARACTER,
    DOUBLE_QUOTED_ESCAPE_PATTERN,
    DOUBLE_QUOTED_ESCAPE_REPLACEMENT,
    DOUBLE_QUOTED_SPECIAL_PATTERN,
    ESCAPED_PAIR_LENGTH,
    ESCAPED_SUBSTITUTION_OPENER,
    ESCAPED_SUBSTITUTION_WORD,
    GROUP_CLOSE_CHARACTER,
    GROUP_OPEN_CHARACTER,
    HEREDOC_START_CHARACTER,
    LINE_FEED,
    NESTED_LINE_BREAK_JOIN,
    SINGLE_QUOTE_INSIDE_SINGLE_QUOTES,
)
from hooks_constants.piped_pytest_blocker_constants import HEREDOC_OPENER_PATTERN
from hooks_constants.shell_command_evaluation_constants import ALL_LINE_BREAK_CHARACTERS
from hooks_constants.shell_command_pipeline import (
    PendingHeredoc,
    closes_the_heredoc,
    pending_heredoc_opened_by,
)
from hooks_constants.shell_command_substitution_constants import (
    COMMAND_SUBSTITUTION_OPENER,
    DOUBLE_QUOTE,
    SHELL_ESCAPE_CHARACTER,
    SINGLE_QUOTE,
)


@dataclass
class _Frame:
    quote: str = ""
    group_depth: int = 0


@dataclass
class _Scan:
    text: str
    index: int = 0
    line_start: int = 0
    all_frames: list[_Frame] = field(default_factory=lambda: [_Frame()])
    all_characters: list[str] = field(default_factory=list)
    all_lines: list[str] = field(default_factory=list)
    all_heredoc_starts: list[int] = field(default_factory=list)


def quote_aware_lines(text: str) -> list[str] | None:
    """Return the logical lines of shell text, ready for a POSIX split, or None.

    ::

        "a ; b<line break>c"        -> ["a ; b", "c"]
        "x=$(a<line break>b)"       -> ["x=$(a;b)"]
        "echo 'it<line break>s'"    -> ["echo 'it<line break>s'"]
        "echo \\"open"               -> None

    Args:
        text: Shell text, such as a Bash tool command or a ``bash -c`` script.

    Returns:
        The non-blank logical lines in order, or None when a quote, group or
        substitution is still open at the end of the text.
    """
    scan = _Scan(text)
    while scan.index < len(text):
        _step(scan)
    _end_line(scan)
    return scan.all_lines if scan.all_frames == [_Frame()] else None


def _step(scan: _Scan) -> None:
    frame = scan.all_frames[-1]
    if frame.quote == SINGLE_QUOTE:
        _step_in_single_quotes(scan, frame)
        return
    if frame.quote == ANSI_C_QUOTE_OPENER:
        _step_in_ansi_c_quotes(scan, frame)
        return
    if frame.quote == DOUBLE_QUOTE:
        _step_in_double_quotes(scan, frame)
        return
    _step_unquoted(scan, frame)


def _is_inside_double_quoted_word(scan: _Scan) -> bool:
    return any(each_frame.quote == DOUBLE_QUOTE for each_frame in scan.all_frames[:-1])


def _emit(scan: _Scan, piece: str, length: int) -> None:
    if _is_inside_double_quoted_word(scan):
        piece = DOUBLE_QUOTED_ESCAPE_PATTERN.sub(DOUBLE_QUOTED_ESCAPE_REPLACEMENT, piece)
    scan.all_characters.append(piece)
    scan.index += length


def _source(scan: _Scan, length: int) -> str:
    return scan.text[scan.index : scan.index + length]


def _step_in_single_quotes(scan: _Scan, frame: _Frame) -> None:
    close_index = scan.text.find(SINGLE_QUOTE, scan.index)
    if close_index < 0:
        _emit(scan, scan.text[scan.index :], len(scan.text) - scan.index)
        return
    frame.quote = ""
    _emit(scan, scan.text[scan.index : close_index + 1], close_index + 1 - scan.index)


def _step_in_ansi_c_quotes(scan: _Scan, frame: _Frame) -> None:
    character = _source(scan, 1)
    if character == SINGLE_QUOTE:
        frame.quote = ""
        _emit(scan, SINGLE_QUOTE, 1)
        return
    if character != SHELL_ESCAPE_CHARACTER:
        _emit(scan, character, 1)
        return
    if _is_inside_double_quoted_word(scan):
        _emit(scan, _source(scan, ESCAPED_PAIR_LENGTH), ESCAPED_PAIR_LENGTH)
        return
    escaped = _source(scan, ESCAPED_PAIR_LENGTH)[1:]
    decoded = ALL_ANSI_C_ESCAPES.get(escaped, SHELL_ESCAPE_CHARACTER + escaped)
    _emit(scan, decoded.replace(SINGLE_QUOTE, SINGLE_QUOTE_INSIDE_SINGLE_QUOTES), ESCAPED_PAIR_LENGTH)


def _step_in_double_quotes(scan: _Scan, frame: _Frame) -> None:
    special_match = DOUBLE_QUOTED_SPECIAL_PATTERN.search(scan.text, scan.index)
    if special_match is None or special_match.start() > scan.index:
        run_end = len(scan.text) if special_match is None else special_match.start()
        _emit(scan, scan.text[scan.index : run_end], run_end - scan.index)
        return
    if _source(scan, 1) == SHELL_ESCAPE_CHARACTER:
        _step_past_escape(scan)
        return
    if scan.text.startswith(COMMAND_SUBSTITUTION_OPENER, scan.index):
        _emit(scan, COMMAND_SUBSTITUTION_OPENER, len(COMMAND_SUBSTITUTION_OPENER))
        scan.all_frames.append(_Frame())
        return
    frame.quote = ""
    _emit(scan, DOUBLE_QUOTE, 1)


def _step_past_escape(scan: _Scan) -> None:
    if _source(scan, ESCAPED_PAIR_LENGTH)[1:] in ALL_LINE_BREAK_CHARACTERS:
        scan.index += ESCAPED_PAIR_LENGTH
        return
    _emit(scan, _source(scan, ESCAPED_PAIR_LENGTH), ESCAPED_PAIR_LENGTH)


def _step_unquoted(scan: _Scan, frame: _Frame) -> None:
    character = _source(scan, 1)
    if character in ALL_LINE_BREAK_CHARACTERS:
        _step_past_line_break(scan)
        return
    if scan.text.startswith(ESCAPED_SUBSTITUTION_OPENER, scan.index):
        _emit(scan, ESCAPED_SUBSTITUTION_WORD, len(ESCAPED_SUBSTITUTION_OPENER))
        return
    if character == SHELL_ESCAPE_CHARACTER:
        _step_past_escape(scan)
        return
    if scan.text.startswith(ANSI_C_QUOTE_OPENER, scan.index):
        _open_ansi_c_quotes(scan, frame)
        return
    if scan.text.startswith(COMMAND_SUBSTITUTION_OPENER, scan.index):
        _emit(scan, COMMAND_SUBSTITUTION_OPENER, len(COMMAND_SUBSTITUTION_OPENER))
        scan.all_frames.append(_Frame())
        return
    if character in (SINGLE_QUOTE, DOUBLE_QUOTE):
        frame.quote = character
        _emit(scan, character, 1)
        return
    if character == COMMENT_START_CHARACTER and _is_word_start(scan):
        _skip_to_line_end(scan)
        return
    _step_plain_character(scan, frame, character)


def _open_ansi_c_quotes(scan: _Scan, frame: _Frame) -> None:
    frame.quote = ANSI_C_QUOTE_OPENER
    opener = ANSI_C_QUOTE_OPENER if _is_inside_double_quoted_word(scan) else SINGLE_QUOTE
    _emit(scan, opener, len(ANSI_C_QUOTE_OPENER))


def _is_word_start(scan: _Scan) -> bool:
    return scan.index == 0 or scan.text[scan.index - 1].isspace()


def _skip_to_line_end(scan: _Scan) -> None:
    while scan.index < len(scan.text) and _source(scan, 1) not in ALL_LINE_BREAK_CHARACTERS:
        scan.index += 1


def _step_plain_character(scan: _Scan, frame: _Frame, character: str) -> None:
    _emit(scan, character, 1)
    if character == HEREDOC_START_CHARACTER:
        scan.all_heredoc_starts.append(scan.index - 1)
        return
    if character == GROUP_OPEN_CHARACTER:
        frame.group_depth += 1
        return
    if character != GROUP_CLOSE_CHARACTER:
        return
    if frame.group_depth:
        frame.group_depth -= 1
        return
    if len(scan.all_frames) > 1:
        scan.all_frames.pop()


def _step_past_line_break(scan: _Scan) -> None:
    pending_heredoc = _pending_heredoc(scan)
    is_crlf = scan.text.startswith(CARRIAGE_RETURN_LINE_BREAK, scan.index)
    length = len(CARRIAGE_RETURN_LINE_BREAK) if is_crlf else 1
    if scan.all_frames == [_Frame()]:
        _end_line(scan)
        scan.index += length
    elif _is_inside_double_quoted_word(scan):
        _emit(scan, _source(scan, length), length)
    else:
        _emit(scan, NESTED_LINE_BREAK_JOIN, length)
    scan.line_start = scan.index
    scan.all_heredoc_starts.clear()
    if pending_heredoc is not None:
        _skip_heredoc_body(scan, pending_heredoc)


def _pending_heredoc(scan: _Scan) -> PendingHeredoc | None:
    for each_start in scan.all_heredoc_starts:
        opener_text = scan.text[each_start : scan.index]
        if HEREDOC_OPENER_PATTERN.match(opener_text):
            return pending_heredoc_opened_by(opener_text)
    return None


def _skip_heredoc_body(scan: _Scan, pending_heredoc: PendingHeredoc) -> None:
    while scan.index < len(scan.text):
        line_end = scan.text.find(LINE_FEED, scan.index)
        line_end = len(scan.text) if line_end < 0 else line_end
        body_line = scan.text[scan.index : line_end].rstrip(CARRIAGE_RETURN)
        scan.index = line_end + 1
        if closes_the_heredoc(body_line, pending_heredoc):
            break
    scan.line_start = scan.index


def _end_line(scan: _Scan) -> None:
    line = "".join(scan.all_characters)
    if line.strip():
        scan.all_lines.append(line)
    scan.all_characters.clear()
