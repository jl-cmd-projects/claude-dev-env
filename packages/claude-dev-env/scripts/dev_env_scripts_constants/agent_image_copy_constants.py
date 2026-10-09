"""Limits and names for the agent_image_copy script."""

from __future__ import annotations

MAXIMUM_LONG_EDGE_PIXELS = 512
VISUAL_TOKEN_PATCH_PIXELS = 28
AGENT_COPY_SUFFIX = ".agent.png"
CROP_BOX_SEPARATOR = ","
CROP_BOX_PART_COUNT = 4
ALL_PNG_WRITABLE_MODES = frozenset({"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"})
PNG_FALLBACK_MODE = "RGB"
