"""Behavioral tests for the image_read_size_gate header offsets and refusal text."""

from __future__ import annotations

import struct

from image_read_size_gate import image_size

from hooks_constants.image_read_size_gate_constants import (
    AGENT_COPY_SCRIPT_PATH,
    ALL_GIF_SIGNATURES,
    JPEG_MARKER_PREFIX,
    JPEG_SIGNATURE,
    MAXIMUM_LONG_EDGE_PIXELS,
    OVERSIZED_IMAGE_REASON_TEMPLATE,
    PNG_SIGNATURE,
)

BASELINE_FRAME_MARKER = 0xC0
SAMPLE_PRECISION = 8


def test_png_offsets_read_the_width_and_height_from_the_ihdr_chunk() -> None:
    ihdr_length = struct.pack(">I", 13)
    png_header = PNG_SIGNATURE + ihdr_length + b"IHDR" + struct.pack(">II", 1440, 2560)

    assert image_size(png_header) == (1440, 2560)


def test_gif_offsets_read_the_little_endian_logical_screen_size() -> None:
    for each_signature in ALL_GIF_SIGNATURES:
        gif_header = each_signature + struct.pack("<HH", 640, 480)

        assert image_size(gif_header) == (640, 480)


def test_jpeg_frame_offsets_read_height_then_width_from_a_baseline_frame() -> None:
    frame_segment = bytes([JPEG_MARKER_PREFIX, BASELINE_FRAME_MARKER]) + struct.pack(
        ">HBHH", 17, SAMPLE_PRECISION, 2560, 1440
    )

    assert image_size(JPEG_SIGNATURE + frame_segment) == (1440, 2560)


def test_agent_copy_script_path_names_the_packaged_script() -> None:
    assert AGENT_COPY_SCRIPT_PATH.is_file()
    assert AGENT_COPY_SCRIPT_PATH.name == "agent_image_copy.py"


def test_reason_template_names_the_size_the_cap_and_the_copy_command() -> None:
    reason = OVERSIZED_IMAGE_REASON_TEMPLATE.format(
        width=1500,
        height=2700,
        maximum_edge=MAXIMUM_LONG_EDGE_PIXELS,
        script_path=AGENT_COPY_SCRIPT_PATH,
        image_path="/tmp/shot.png",
    )

    assert "1500x2700" in reason
    assert f"{MAXIMUM_LONG_EDGE_PIXELS} pixels" in reason
    assert f'python3 "{AGENT_COPY_SCRIPT_PATH}" "/tmp/shot.png"' in reason
