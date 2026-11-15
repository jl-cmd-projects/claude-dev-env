"""Read the text of a file a session sends to the user, for the sent file question gate.

A small file is read whole. A large file is read through its first and last
128 KB, so a question at either end is still found and the read stays
fast::

    a 3 KB notes.md                  -> its whole text
    a 2 MB report.md                 -> its first 128 KB, a blank line, its last 128 KB
    a .md file holding binary data   -> None

``plain_page_text`` turns an HTML page into its shown text in one pass over
its tags, with no parser, for the gate's second read.
"""

from __future__ import annotations

import codecs
import html
import os
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.sent_file_question_gate_constants import (
    BINARY_READ_MODE,
    BLOCK_BREAK,
    CLOSING_TAG_MARK,
    LINE_BREAK,
    PLAIN_HEADING_BREAK,
    SPACE,
    SPACE_RUN_PATTERN,
    TAG_CLOSE,
    TAG_OPEN,
    FILE_PART_BYTES,
    FILE_PARTS_SEPARATOR,
    MAXIMUM_UTF8_CONTINUATION_BYTES,
    MAXIMUM_WHOLE_FILE_BYTES,
    NUL_BYTE,
    UTF8_CONTINUATION_BYTES,
    UTF8_ENCODING,
)
from hooks_constants.user_step_wording_constants import (
    ALL_HTML_HEADING_TAGS,
    ALL_HTML_HIDDEN_TAGS,
    ALL_HTML_INLINE_TAGS,
    HTML_LINE_BREAK_TAG,
)
from user_step_wording import sent_file_location


def _decoded_part(part_bytes: bytes, is_cut_at_end: bool) -> str:
    decoder = codecs.getincrementaldecoder(UTF8_ENCODING)()
    return decoder.decode(part_bytes, final=not is_cut_at_end)


def _tail_without_split_character(tail_bytes: bytes) -> bytes:
    cut_length = 0
    while (
        cut_length < MAXIMUM_UTF8_CONTINUATION_BYTES
        and cut_length < len(tail_bytes)
        and tail_bytes[cut_length] in UTF8_CONTINUATION_BYTES
    ):
        cut_length += 1
    return tail_bytes[cut_length:]


def _head_and_tail_bytes(file_path: Path) -> tuple[bytes, bytes]:
    with file_path.open(BINARY_READ_MODE) as sent_file:
        head_bytes = sent_file.read(MAXIMUM_WHOLE_FILE_BYTES + 1)
        if len(head_bytes) <= MAXIMUM_WHOLE_FILE_BYTES:
            return head_bytes, b""
        sent_file.seek(-FILE_PART_BYTES, os.SEEK_END)
        return head_bytes[:FILE_PART_BYTES], _tail_without_split_character(
            sent_file.read(FILE_PART_BYTES)
        )


def sent_file_scan_text(file_path_text: str, working_directory: object) -> str | None:
    """Return the text the gate reads from a sent file, or None when it reads none.

    ::

        a 3 KB notes.md                  -> its whole text
        a 2 MB report.md                 -> its first 128 KB, a blank line, its last 128 KB
        a .md file holding binary data   -> None
        shot.png, a folder, a lost path  -> None

    A file that holds a NUL byte or is not valid UTF-8 gives None, so the
    gate never quotes garbled bytes.

    Args:
        file_path_text: The path the tool call names.
        working_directory: The session's ``cwd`` from the hook payload.

    Returns:
        The decoded text, or None.
    """
    file_path = sent_file_location(file_path_text, working_directory)
    if file_path is None:
        return None
    try:
        head_bytes, tail_bytes = _head_and_tail_bytes(file_path)
    except (OSError, ValueError):
        return None
    if NUL_BYTE in head_bytes or NUL_BYTE in tail_bytes:
        return None
    try:
        head_text = _decoded_part(head_bytes, is_cut_at_end=bool(tail_bytes))
        tail_text = _decoded_part(tail_bytes, is_cut_at_end=False)
    except UnicodeDecodeError:
        return None
    return head_text + FILE_PARTS_SEPARATOR + tail_text if tail_text else head_text


def sent_file_is_partly_read(file_path_text: str, working_directory: object) -> bool:
    """Return True when ``sent_file_scan_text`` reads only the start and end of the file.

    ::

        a 3 KB notes.md      -> False
        a 2 MB report.md     -> True
        shot.png, lost path  -> False

    Args:
        file_path_text: The path the tool call names.
        working_directory: The session's ``cwd`` from the hook payload.

    Returns:
        True for a sent text file over 256 KB.
    """
    file_path = sent_file_location(file_path_text, working_directory)
    if file_path is None:
        return False
    try:
        return file_path.stat().st_size > MAXIMUM_WHOLE_FILE_BYTES
    except OSError:
        return False


def _tag_name(tag_body: str) -> str:
    all_name_words = tag_body.lstrip(CLOSING_TAG_MARK).split(None, 1)
    return all_name_words[0].rstrip(CLOSING_TAG_MARK).lower() if all_name_words else ""


def _after_tag(tag_body: str, hidden_tag_name: str) -> tuple[str, str]:
    is_closing = tag_body.startswith(CLOSING_TAG_MARK)
    tag_name = _tag_name(tag_body)
    if hidden_tag_name:
        return ("" if is_closing and tag_name == hidden_tag_name else hidden_tag_name), ""
    if not is_closing and tag_name in ALL_HTML_HIDDEN_TAGS:
        return tag_name, ""
    if tag_name in ALL_HTML_HEADING_TAGS and not is_closing:
        return "", PLAIN_HEADING_BREAK
    if tag_name == HTML_LINE_BREAK_TAG:
        return "", LINE_BREAK
    if tag_name in ALL_HTML_INLINE_TAGS:
        return "", ""
    return "", BLOCK_BREAK


def plain_page_text(page_markup: str) -> str:
    """Return the shown text of an HTML page through one pass over its tags, with no parser.

    ::

        <h2>Plan</h2><p>Should I merge it?</p>   -> "\\n\\n# Plan\\n\\n\\n\\nShould I merge it?\\n\\n"
        <script>var x = 'Should I?'</script>      -> ""
        <script <script <script ...               -> "" (an unclosed tag ends the text)

    The gate falls back to this read when the HTML parser does not finish in
    time. Each character is visited once. A heading or ``summary`` starts a
    "# " line, another block tag starts a paragraph, and the contents of
    script, style, code, pre, blockquote, and the other hidden tags are left
    out. Character references are decoded.

    Args:
        page_markup: The HTML page source.

    Returns:
        The shown text as Markdown-like paragraphs.
    """
    all_parts: list[str] = []
    hidden_tag_name = ""
    position = 0
    while position < len(page_markup):
        tag_start = page_markup.find(TAG_OPEN, position)
        text_end = len(page_markup) if tag_start == -1 else tag_start
        if not hidden_tag_name:
            all_parts.append(SPACE_RUN_PATTERN.sub(SPACE, page_markup[position:text_end]))
        tag_end = -1 if tag_start == -1 else page_markup.find(TAG_CLOSE, tag_start)
        if tag_end == -1:
            break
        hidden_tag_name, tag_break = _after_tag(
            page_markup[tag_start + 1 : tag_end].strip(), hidden_tag_name
        )
        all_parts.append(tag_break)
        position = tag_end + 1
    return html.unescape("".join(all_parts))
