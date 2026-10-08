"""Write a copy of an image small enough for an agent to read.

The image_read_size_gate hook refuses a Read of an image whose long edge is over
512 pixels and names this script. The script writes ``<name>.agent.png`` next to
the source, scaled so the long edge is 512 pixels with the aspect ratio kept,
and prints its path::

    python3 agent_image_copy.py shot.png               -> shot.agent.png (288x512)
    python3 agent_image_copy.py shot.png --crop 0,0,720,640
                                                       -> the top-left region, capped
    python3 agent_image_copy.py icon.png (200x200)     -> icon.agent.png, same size

The copy is newer than the source, so a check that wants a screenshot read
after a page changed still counts it.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

scripts_directory = str(Path(__file__).resolve().parent)
if scripts_directory not in sys.path:
    sys.path.insert(0, scripts_directory)

from dev_env_scripts_constants.agent_image_copy_constants import (
    AGENT_COPY_SUFFIX,
    CROP_BOX_PART_COUNT,
    CROP_BOX_SEPARATOR,
    MAXIMUM_LONG_EDGE_PIXELS,
    VISUAL_TOKEN_PATCH_PIXELS,
)
from PIL import Image


def capped_size(
    width: int, height: int, maximum_edge: int = MAXIMUM_LONG_EDGE_PIXELS
) -> tuple[int, int]:
    """Return the size that fits the long edge into maximum_edge with the aspect ratio kept.

    ::

        capped_size(1440, 2560) -> (288, 512)
        capped_size(2000, 1000) -> (512, 256)
        capped_size(300, 200)   -> (300, 200)

    Args:
        width: Source width in pixels.
        height: Source height in pixels.
        maximum_edge: The largest long edge allowed.

    Returns:
        The capped (width, height).
    """
    long_edge = max(width, height)
    if long_edge <= maximum_edge:
        return width, height
    scale = maximum_edge / long_edge
    return max(1, round(width * scale)), max(1, round(height * scale))


def visual_tokens(width: int, height: int) -> int:
    """Return the documented visual-token cost of an image: one token per 28x28 patch.

    ::

        visual_tokens(1440, 2560) -> 4784
        visual_tokens(288, 512)   -> 209

    Args:
        width: Image width in pixels as the model sees it.
        height: Image height in pixels as the model sees it.
    """
    return math.ceil(width / VISUAL_TOKEN_PATCH_PIXELS) * math.ceil(
        height / VISUAL_TOKEN_PATCH_PIXELS
    )


def parse_all_crop_coordinates(crop_text: str) -> tuple[int, int, int, int]:
    """Return LEFT, TOP, RIGHT, BOTTOM parsed from text like ``0,0,720,640``.

    Args:
        crop_text: Four comma-separated pixel coordinates.

    Returns:
        The four coordinates as integers.

    Raises:
        argparse.ArgumentTypeError: When the text does not hold four numbers.
    """
    all_parts = crop_text.split(CROP_BOX_SEPARATOR)
    if len(all_parts) != CROP_BOX_PART_COUNT:
        raise argparse.ArgumentTypeError(
            f"--crop takes LEFT,TOP,RIGHT,BOTTOM, got {crop_text!r}"
        )
    left, top, right, bottom = (int(each_part) for each_part in all_parts)
    return left, top, right, bottom


def write_agent_copy(
    source_path: Path, all_crop_coordinates: tuple[int, int, int, int] | None = None
) -> Path:
    """Write the capped copy beside the source and return its path.

    Args:
        source_path: The full-size image.
        all_crop_coordinates: An optional LEFT, TOP, RIGHT, BOTTOM region cut before scaling.

    Returns:
        The path of the written copy.
    """
    copy_path = source_path.with_name(source_path.stem + AGENT_COPY_SUFFIX)
    with Image.open(source_path) as source_image:
        working_image = source_image.crop(all_crop_coordinates) if all_crop_coordinates else source_image.copy()
    working_image = working_image.resize(
        capped_size(*working_image.size), Image.Resampling.LANCZOS
    )
    working_image.save(copy_path, optimize=True)
    return copy_path


def main(all_arguments: list[str]) -> int:
    """Write the capped copy named on the command line and print its path and token cost.

    Args:
        all_arguments: Command-line arguments after the program name.

    Returns:
        0 when the copy was written.
    """
    parser = argparse.ArgumentParser(
        description="Write an agent-size copy of an image."
    )
    parser.add_argument("image_path", type=Path)
    parser.add_argument("--crop", type=parse_all_crop_coordinates, default=None)
    parsed = parser.parse_args(all_arguments)
    copy_path = write_agent_copy(parsed.image_path, parsed.crop)
    with Image.open(copy_path) as copy_image:
        width, height = copy_image.size
    print(f"{copy_path} {width}x{height} about {visual_tokens(width, height)} tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
