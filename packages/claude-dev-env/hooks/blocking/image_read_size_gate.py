#!/usr/bin/env python3
"""PreToolUse hook: refuse a Read of an image larger than the agent cap.

A Read of an image puts the whole picture in the context. A phone screenshot
at 1440x2560 costs about 4,784 tokens, the most one image can cost. The hook
reads the width and height from the file header and refuses the Read when the
long edge passes the cap, naming the command that writes a capped copy::

    Read shot.png (1440x2560)        -> refused, names agent_image_copy.py
    Read shot.agent.png (288x512)    -> allowed
    Read notes.md                    -> allowed
    Read broken.png (no header)      -> allowed

A missing file, a WebP or other unknown format and an unreadable header all pass, so the
hook never fails closed.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.image_read_size_gate_constants import (
    AGENT_COPY_SCRIPT_PATH,
    ALL_JPEG_FRAME_MARKERS,
    ALL_JPEG_STANDALONE_MARKERS,
    DENY_DECISION,
    FILE_PATH_INPUT_KEY,
    ALL_GIF_SIGNATURES,
    HEADER_BYTE_COUNT,
    JPEG_FRAME_SIZE_END,
    JPEG_FRAME_SIZE_START,
    JPEG_MARKER_LENGTH,
    JPEG_MARKER_PREFIX,
    JPEG_SIGNATURE,
    MAXIMUM_LONG_EDGE_PIXELS,
    OVERSIZED_IMAGE_REASON_TEMPLATE,
    PERMISSION_DECISION_REASON_KEY,
    PNG_SIGNATURE,
    PRE_TOOL_USE_EVENT_NAME,
    READ_TOOL_NAME,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def _jpeg_size(header: bytes) -> tuple[int, int] | None:
    offset = len(JPEG_SIGNATURE)
    while offset + JPEG_FRAME_SIZE_END <= len(header):
        if header[offset] != JPEG_MARKER_PREFIX:
            return None
        marker = header[offset + 1]
        if marker == JPEG_MARKER_PREFIX:
            offset += 1
            continue
        if marker in ALL_JPEG_STANDALONE_MARKERS:
            offset += JPEG_MARKER_LENGTH
            continue
        if marker in ALL_JPEG_FRAME_MARKERS:
            height, width = struct.unpack(
                ">HH", header[offset + JPEG_FRAME_SIZE_START : offset + JPEG_FRAME_SIZE_END]
            )
            return width, height
        segment_length_end = offset + JPEG_MARKER_LENGTH + JPEG_MARKER_LENGTH
        offset += JPEG_MARKER_LENGTH + struct.unpack(">H", header[offset + JPEG_MARKER_LENGTH : segment_length_end])[0]
    return None


def image_size(header: bytes) -> tuple[int, int] | None:
    """Return (width, height) read from the first bytes of a PNG, JPEG or GIF file.

    ::

        PNG header of a 1440x2560 file -> (1440, 2560)
        b"plain text"                  -> None

    Args:
        header: The first bytes of the file.
    """
    if header.startswith(PNG_SIGNATURE) and len(header) >= 24:
        width, height = struct.unpack(">II", header[16:24])
        return width, height
    if header.startswith(ALL_GIF_SIGNATURES) and len(header) >= 10:
        width, height = struct.unpack("<HH", header[6:10])
        return width, height
    if header.startswith(JPEG_SIGNATURE):
        return _jpeg_size(header)
    return None


def _read_header(file_path: str) -> bytes:
    try:
        with open(file_path, "rb") as image_file:
            return image_file.read(HEADER_BYTE_COUNT)
    except OSError:
        return b""


def oversized_image_reason(all_hook_fields: dict[str, object]) -> str | None:
    """Return the refusal for a Read of an image over the cap, or None to allow it.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    if all_hook_fields.get(TOOL_NAME_KEY) != READ_TOOL_NAME or not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get(FILE_PATH_INPUT_KEY)
    if not isinstance(file_path, str):
        return None
    dimensions = image_size(_read_header(file_path))
    if dimensions is None or max(dimensions) <= MAXIMUM_LONG_EDGE_PIXELS:
        return None
    width, height = dimensions
    return OVERSIZED_IMAGE_REASON_TEMPLATE.format(
        width=width,
        height=height,
        maximum_edge=MAXIMUM_LONG_EDGE_PIXELS,
        script_path=AGENT_COPY_SCRIPT_PATH,
        image_path=file_path,
    )


def main() -> int:
    """Read the PreToolUse payload and print a deny decision for an oversized image.

    Returns:
        0 in every case; the decision travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return 0
    refusal_reason = oversized_image_reason(hook_payload)
    if refusal_reason is not None:
        sys.stdout.write(
            json.dumps(
                {
                    HOOK_SPECIFIC_OUTPUT_KEY: {
                        HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
                        PERMISSION_DECISION_KEY: DENY_DECISION,
                        PERMISSION_DECISION_REASON_KEY: refusal_reason,
                    }
                }
            )
        )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
