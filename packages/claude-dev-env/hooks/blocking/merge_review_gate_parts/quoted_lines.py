"""Cut shell text into the logical lines bash reads, with each quoted region kept whole.

::

    gh pr create --body $'it\\'s' ; gh pr create  -> one line, $'it\\'s' as 'it'\\''s'
    bash -c "true<line break>gh pr create"       -> one line; the line break stays in the word
    gh pr create --body "$(echo '"')"            -> one line; the inner quote is escaped
    echo 'open                                   -> None

A line break ends a logical line only outside every quote, subshell and
substitution. Inside a subshell or a substitution outside quotes it becomes
``;``. A ``$'...'`` word becomes a single-quoted word, with its escapes
decoded as bash decodes them. An escaped ``\\$(`` outside quotes keeps its
``(`` in the word. Inside a substitution in a double-quoted word, each quote
and backslash gets a backslash. So a POSIX ``shlex`` split of each line gives
the words bash gives. Comments and heredoc bodies are dropped.

``expansion_marked_line`` reads the quotes of one such line and marks each
character bash may expand, so each word can be judged on its own quoting.
``holds_unquoted_expansion`` reads raw text to tell whether bash would expand
a brace, a glob or a tilde anywhere in it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_ANSI_C_ESCAPES,
    ALL_EXPANSION_OPENER_CHARACTERS,
    ANSI_C_NUMERIC_ESCAPE_PATTERN,
    ANSI_C_STRING_END_CHARACTER,
    ASCII_MAXIMUM,
    BYTE_MASK,
    CONTROL_CHARACTER_MASK,
    EXPANSION_START_CHARACTER,
    HEX_BASE,
    OCTAL_BASE,
    PARAMETER_BRACE_CLOSE,
    PARAMETER_BRACE_OPEN,
    QUOTED_EXPANSION_MARK,
    SPLITTING_PARAMETER_CHARACTER,
    SURROGATE_FIRST,
    SURROGATE_LAST,
    UNREADABLE_WORD_MARK,
    EXTENDED_GLOB_OPENER_PATTERN,
    ALL_SHELL_EXPANSION_CHARACTERS,
    ALL_SHELL_WORD_START_CHARACTERS,
    ANSI_C_QUOTE_OPENER,
    ANSI_C_QUOTE_PREFIX,
    TILDE_CHARACTER,
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
    BACKTICK,
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


@dataclass
class _ExpansionScan:
    text: str
    index: int = 0
    quote: str = ""
    is_word_start: bool = True
    is_after_dollar: bool = False


def holds_unquoted_expansion(text: str) -> bool:
    """Return whether bash would expand a brace, a glob or a tilde somewhere in shell text.

    ::

        gh pr create --ba{se=a,se=b}     -> True, two --base words reach gh
        gh pr create --b?se=x            -> True, gh gets the name of a matching file
        gh pr create --fill ~            -> True, gh gets $HOME
        gh pr create --he@(ad=x)         -> True, an extended glob under bash -O extglob
        gh pr create --title '[x] {y}?'  -> False, quoted
        gh pr create --head \\{a,b\\}      -> False, escaped
        gh pr create --base=~            -> False, the ~ starts no word

    A quote that never closes also counts, since the reading is unsure.
    Each level of nesting, such as the text of ``bash -c``, needs its own call.

    Args:
        text: One level of shell text.

    Returns:
        True when an unquoted ``{ } * ? [``, an ``@(``, ``+(`` or ``!(``, or a
        word-leading ``~`` is found.
    """
    scan = _ExpansionScan(text)
    while scan.index < len(text):
        if _is_expansion_step(scan):
            return True
    return bool(scan.quote)


def _is_expansion_step(scan: _ExpansionScan) -> bool:
    if scan.quote:
        _step_inside_expansion_quote(scan)
        return False
    return _is_unquoted_expansion_at(scan)


def _step_inside_expansion_quote(scan: _ExpansionScan) -> None:
    character = scan.text[scan.index]
    if character == SHELL_ESCAPE_CHARACTER and scan.quote != SINGLE_QUOTE:
        scan.index += ESCAPED_PAIR_LENGTH
        return
    if character == scan.quote[-1]:
        scan.quote = ""
    scan.index += 1
    scan.is_word_start = False


def _is_unquoted_expansion_at(scan: _ExpansionScan) -> bool:
    character = scan.text[scan.index]
    if character == SHELL_ESCAPE_CHARACTER:
        scan.index += ESCAPED_PAIR_LENGTH
        scan.is_word_start = scan.is_after_dollar = False
        return False
    if character in ALL_SHELL_EXPANSION_CHARACTERS or (character == TILDE_CHARACTER and scan.is_word_start):
        return True
    if _opens_extended_glob(scan):
        return True
    if character == SINGLE_QUOTE:
        scan.quote = ANSI_C_QUOTE_OPENER if scan.is_after_dollar else SINGLE_QUOTE
    elif character == DOUBLE_QUOTE:
        scan.quote = DOUBLE_QUOTE
    scan.is_word_start = character.isspace() or character in ALL_SHELL_WORD_START_CHARACTERS
    scan.is_after_dollar = character == ANSI_C_QUOTE_PREFIX
    scan.index += 1
    return False


def _opens_extended_glob(scan: _ExpansionScan) -> bool:
    return EXTENDED_GLOB_OPENER_PATTERN.match(scan.text, scan.index) is not None


def expansion_marked_line(line: str) -> str:
    """Return one logical line with each character bash may expand put as a mark, at the same place.

    The line comes from ``quote_aware_lines``, so its quotes are balanced and
    a ``$'...'`` value is already a single-quoted word. Two marks stand in::

        $X, $(x), `x`, $"x", { } * ? [, @( +( !(, a word-leading ~, outside quotes -> UNREADABLE_WORD_MARK
        "$@", "${a[@]}" inside double quotes                                    -> UNREADABLE_WORD_MARK
        "$X", "$(x)", "`x`" inside double quotes                                -> QUOTED_EXPANSION_MARK
        'a $X {b}', \\$X, \\*                                                    -> left as written

    An unreadable mark means bash may split the word or change it into
    other words. A quoted mark means bash keeps one word whose text the
    gate cannot read. Only marked characters change, and no mark is a quote,
    a backslash, a space or an operator, so a POSIX split of the marked line
    gives the same words, in the same places, as the line itself.

    Args:
        line: One logical line from ``quote_aware_lines``.

    Returns:
        The line with the same length, marks in place of the expanding characters.
    """
    all_characters = list(line)
    quote = ""
    index = 0
    while index < len(line):
        if line[index] == SHELL_ESCAPE_CHARACTER and quote != SINGLE_QUOTE:
            index += ESCAPED_PAIR_LENGTH
            continue
        quote, mark = _marked_step(line, index, quote)
        all_characters[index] = mark or line[index]
        index += 1
    return "".join(all_characters)


def _marked_step(line: str, index: int, quote: str) -> tuple[str, str | None]:
    character = line[index]
    if quote == SINGLE_QUOTE:
        return ("" if character == SINGLE_QUOTE else quote), None
    if quote == DOUBLE_QUOTE:
        return ("" if character == DOUBLE_QUOTE else quote), _quoted_expansion_mark(line, index)
    if character in (SINGLE_QUOTE, DOUBLE_QUOTE):
        return character, None
    return quote, (UNREADABLE_WORD_MARK if _is_unquoted_expansion(line, index) else None)


def _quoted_expansion_mark(line: str, index: int) -> str | None:
    character = line[index]
    if character == BACKTICK:
        return QUOTED_EXPANSION_MARK
    if character != EXPANSION_START_CHARACTER:
        return None
    following = line[index + 1 : index + ESCAPED_PAIR_LENGTH]
    if following == SPLITTING_PARAMETER_CHARACTER:
        return UNREADABLE_WORD_MARK
    if following == PARAMETER_BRACE_OPEN:
        brace_end = line.find(PARAMETER_BRACE_CLOSE, index)
        parameter = line[index : brace_end if brace_end >= 0 else len(line)]
        if SPLITTING_PARAMETER_CHARACTER in parameter:
            return UNREADABLE_WORD_MARK
    return QUOTED_EXPANSION_MARK


def _is_unquoted_expansion(line: str, index: int) -> bool:
    character = line[index]
    if character in ALL_EXPANSION_OPENER_CHARACTERS or character in ALL_SHELL_EXPANSION_CHARACTERS:
        return True
    if character == TILDE_CHARACTER:
        return index == 0 or line[index - 1].isspace() or line[index - 1] in ALL_SHELL_WORD_START_CHARACTERS
    return EXTENDED_GLOB_OPENER_PATTERN.match(line, index) is not None


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
    decoded, length = _decoded_ansi_c_escape(scan.text, scan.index)
    if decoded == ANSI_C_STRING_END_CHARACTER:
        _skip_to_ansi_c_quote_end(scan)
        return
    _emit(scan, decoded.replace(SINGLE_QUOTE, SINGLE_QUOTE_INSIDE_SINGLE_QUOTES), length)


def _decoded_ansi_c_escape(text: str, index: int) -> tuple[str, int]:
    """Return the text bash makes of the backslash escape at ``index`` in a ``$'...'`` value, and its length.

    ::

        \\n, \\', \\\\        -> line break, quote, backslash; 2 characters
        \\x61, \\101, \\u0041 -> "a", "A", "A"
        \\cA                  -> the control character 0x01
        \\x with no digit, \\q -> kept as written, backslash and all
        \\xff, \\377, \\ud800   -> UNREADABLE_WORD_MARK, a byte or code point the gate does not spell

    A ``\\0`` ends the value, as in bash; the caller drops the rest of it.
    """
    escaped = text[index + 1 : index + ESCAPED_PAIR_LENGTH]
    if escaped in ALL_ANSI_C_ESCAPES:
        return ALL_ANSI_C_ESCAPES[escaped], ESCAPED_PAIR_LENGTH
    numeric_match = ANSI_C_NUMERIC_ESCAPE_PATTERN.match(text, index)
    if numeric_match is None:
        return SHELL_ESCAPE_CHARACTER + escaped, ESCAPED_PAIR_LENGTH
    return _numeric_escape_text(numeric_match), numeric_match.end() - index


def _numeric_escape_text(numeric_match: re.Match[str]) -> str:
    if numeric_match["control"] is not None:
        return chr(ord(numeric_match["control"]) & CONTROL_CHARACTER_MASK)
    byte_digits = numeric_match["octal"] or numeric_match["hex"]
    if byte_digits is not None:
        byte_value = int(byte_digits, OCTAL_BASE if numeric_match["octal"] else HEX_BASE) & BYTE_MASK
        return chr(byte_value) if byte_value <= ASCII_MAXIMUM else UNREADABLE_WORD_MARK
    code_point = int(numeric_match["short_unicode"] or numeric_match["long_unicode"], HEX_BASE)
    if code_point > sys.maxunicode or SURROGATE_FIRST <= code_point <= SURROGATE_LAST:
        return UNREADABLE_WORD_MARK
    return chr(code_point)


def _skip_to_ansi_c_quote_end(scan: _Scan) -> None:
    while scan.index < len(scan.text) and _source(scan, 1) != SINGLE_QUOTE:
        scan.index += ESCAPED_PAIR_LENGTH if _source(scan, 1) == SHELL_ESCAPE_CHARACTER else 1


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
