"""Read transcript lines for the closing question round gate, with a clock check before each one.

::

    b'{"a": 1}\\n{"b": 2}'                    -> ['{"a": 1}', '{"b": 2}']
    b'{"\\\\u0074urnOrigin": "sdk"}'          -> ['{"turnOrigin": "sdk"}']
    a 200 MB line between two lines          -> [first line, "", last line]

The gate's substring scans run on these lines, so each line reaches them with
escapes of printable ASCII spelled out and no byte order mark.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.closing_question_round_gate_constants import (
    ESCAPED_ASCII_TEXT,
    ESCAPED_PRINTABLE_ASCII_PATTERN,
    LINE_FEED_BYTES,
    MAXIMUM_SCANNED_BYTES,
    MAXIMUM_SCANNED_TEXT_BYTES,
)
from hooks_constants.open_tasks_stop_gate_constants import UTF8_ENCODING
from hooks_constants.setup_project_paths_constants import (
    DECODE_ERRORS_POLICY,
    UTF8_BYTE_ORDER_MARK,
)
from open_tasks_transcript_records import parsed_object

ScannedItem = TypeVar("ScannedItem")


def before_deadline(all_items: Iterable[ScannedItem], deadline_at: float) -> Iterator[ScannedItem]:
    """Yield each text, line, or match in order, and raise TimeoutError once the monotonic clock reaches the deadline.

    The clock is read before each item is yielded.
    """
    for each_item in all_items:
        if time.monotonic() >= deadline_at:
            raise TimeoutError
        yield each_item


def is_within_scan_cap(scanned_text: str) -> bool:
    """Return True when the text holds 2 MiB or less once encoded as UTF-8."""
    return len(scanned_text) <= MAXIMUM_SCANNED_TEXT_BYTES and (
        len(scanned_text.encode(UTF8_ENCODING, DECODE_ERRORS_POLICY)) <= MAXIMUM_SCANNED_TEXT_BYTES
    )


def transcript_lines(transcript_path: object, deadline_at: float) -> list[str]:
    """Return the transcript file's lines, with each line over 16 MiB read as an empty line.

    ::

        b'{"a": 1}\\n{"b": 2}'            -> ['{"a": 1}', '{"b": 2}']
        a 200 MB line between two lines  -> [first line, "", last line]
        no string, or a missing file     -> []

    The file is read as bytes and cut at each line feed. Each line of 16 MiB or
    less is decoded as UTF-8 with bad bytes replaced, and the empty stand-in
    keeps the positions of the lines after it. A byte order mark at the start
    of a line is dropped. A line that holds an escape of a printable ASCII
    character, ``\\u0020`` to ``\\u007f``, and parses as a JSON object is
    written out again without escapes for printable characters,
    so ``"\\u0074urnOrigin"`` reads as ``"turnOrigin"`` for the substring
    checks that run before each parse. The clock is read before each line, and
    TimeoutError is raised once it reaches ``deadline_at``.
    """
    if not isinstance(transcript_path, str):
        return []
    try:
        transcript_bytes = Path(transcript_path).read_bytes()
    except (OSError, ValueError):
        return []
    return [
        _scannable_line(each_line)
        for each_line in before_deadline(transcript_bytes.split(LINE_FEED_BYTES), deadline_at)
    ]


def _scannable_line(line_bytes: bytes) -> str:
    if len(line_bytes) > MAXIMUM_SCANNED_BYTES:
        return ""
    line_text = line_bytes.decode(UTF8_ENCODING, DECODE_ERRORS_POLICY).removeprefix(
        UTF8_BYTE_ORDER_MARK
    )
    if ESCAPED_ASCII_TEXT not in line_text or not ESCAPED_PRINTABLE_ASCII_PATTERN.search(line_text):
        return line_text
    each_record = parsed_object(line_text)
    if each_record is None:
        return line_text
    try:
        return json.dumps(each_record, ensure_ascii=False)
    except (RecursionError, ValueError):
        return line_text
