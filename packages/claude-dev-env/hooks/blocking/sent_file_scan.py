"""Read the text of a file a session sends to the user, for the sent file question gate.

A small file is read whole. A large file is read through its first and last
128 KB, so a question at either end is still found and the read stays
fast::

    a 3 KB notes.md                  -> its whole text
    a 2 MB report.md                 -> its first 128 KB, a blank line, its last 128 KB
    a .md file holding binary data   -> None
"""

from __future__ import annotations

import codecs
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
    FILE_PART_BYTES,
    FILE_PARTS_SEPARATOR,
    MAXIMUM_UTF8_CONTINUATION_BYTES,
    MAXIMUM_WHOLE_FILE_BYTES,
    NUL_BYTE,
    UTF8_CONTINUATION_BYTES,
    UTF8_ENCODING,
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
