"""Constants for the SessionStart restore_dev_null hook.

``/dev/null`` is character device 1:3 on Linux. Other platforms use other
device numbers, so the hook acts only when the platform tag is Linux.
"""

from __future__ import annotations

__all__ = [
    "DEV_NULL_MAJOR",
    "DEV_NULL_MINOR",
    "DEV_NULL_MODE",
    "DEV_NULL_PATH",
    "LINUX_PLATFORM_TAG",
    "MKNOD_TIMEOUT_SECONDS",
    "NON_LINUX_SKIP_LINE",
]

DEV_NULL_PATH = "/dev/null"
DEV_NULL_MAJOR = 1
DEV_NULL_MINOR = 3
DEV_NULL_MODE = "666"
MKNOD_TIMEOUT_SECONDS = 5
LINUX_PLATFORM_TAG = "linux"
NON_LINUX_SKIP_LINE = "/dev/null check skipped: device node 1:3 is Linux-only."
