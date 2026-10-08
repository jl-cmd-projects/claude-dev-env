"""Names, limits and refusal text for the image_read_size_gate PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

READ_TOOL_NAME = "Read"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
FILE_PATH_INPUT_KEY = "file_path"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
MAXIMUM_LONG_EDGE_PIXELS = 512
HEADER_BYTE_COUNT = 64 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ALL_GIF_SIGNATURES = (b"GIF87a", b"GIF89a")
JPEG_SIGNATURE = b"\xff\xd8"
RIFF_SIGNATURE = b"RIFF"
WEBP_SIGNATURE = b"WEBP"
JPEG_MARKER_PREFIX = 0xFF
JPEG_MARKER_LENGTH = 2
JPEG_FRAME_SIZE_START = 5
JPEG_FRAME_SIZE_END = 9
ALL_JPEG_FRAME_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
ALL_JPEG_STANDALONE_MARKERS = frozenset(
    {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8}
)
AGENT_COPY_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "agent_image_copy.py"
OVERSIZED_IMAGE_REASON_TEMPLATE = (
    "This image is {width}x{height} pixels. Agents read images at {maximum_edge} pixels or less"
    " on the long edge, because a full-size image fills the context: a 1440x2560 screenshot costs"
    " about 4,784 tokens, and a 288x512 copy costs about 209. Write a capped copy and read that"
    ' copy: `python3 "{script_path}" "{image_path}"` prints the path of the copy, which keeps'
    " the aspect ratio. Crop the region you need with `--crop LEFT,TOP,RIGHT,BOTTOM` when a"
    " detail is too small at that size. Send the full-size file to a person, never to an agent."
)
