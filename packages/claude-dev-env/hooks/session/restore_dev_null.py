#!/usr/bin/env python3
"""SessionStart hook — restores /dev/null when a command has replaced it.

A command that removes or overwrites ``/dev/null`` leaves a regular file at that
path, so later shell redirects such as ``2>/dev/null`` write into that file.
At session start this hook checks the path. When it is not the character device
1:3, the hook removes the entry and recreates it with
``mknod -m 666 /dev/null c 1 3``. A healthy path is left unchanged.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Callable
from types import SimpleNamespace

DEV_NULL_PATH = "/dev/null"
DEV_NULL_MAJOR = 1
DEV_NULL_MINOR = 3
DEV_NULL_MODE = "666"
MKNOD_TIMEOUT_SECONDS = 5
WINDOWS_PLATFORM_TAG = "win32"
WINDOWS_SKIP_LINE = "/dev/null check skipped: Windows has no /dev/null device node."


def is_dev_null_device(
    device_path: str,
    read_status: Callable[[str], os.stat_result | SimpleNamespace] = os.lstat,
) -> bool:
    try:
        device_status = read_status(device_path)
    except OSError:
        return False
    if not stat.S_ISCHR(device_status.st_mode):
        return False
    return (
        os.major(device_status.st_rdev) == DEV_NULL_MAJOR
        and os.minor(device_status.st_rdev) == DEV_NULL_MINOR
    )


def restore_dev_null(
    device_path: str = DEV_NULL_PATH,
    read_status: Callable[[str], os.stat_result | SimpleNamespace] = os.lstat,
) -> str:
    if is_dev_null_device(device_path, read_status):
        return f"{device_path} is character device {DEV_NULL_MAJOR}:{DEV_NULL_MINOR}; no change."
    try:
        if os.path.lexists(device_path):
            os.remove(device_path)
        subprocess.run(
            [
                "mknod",
                "-m",
                DEV_NULL_MODE,
                device_path,
                "c",
                str(DEV_NULL_MAJOR),
                str(DEV_NULL_MINOR),
            ],
            check=True,
            capture_output=True,
            timeout=MKNOD_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as failure:
        failure_detail = (failure.stderr or b"").decode(errors="replace").strip()
        return f"could not restore {device_path}: {failure_detail or failure}"
    except (OSError, subprocess.SubprocessError) as failure:
        return f"could not restore {device_path}: {failure}"
    return f"restored {device_path} as character device {DEV_NULL_MAJOR}:{DEV_NULL_MINOR}."


def main() -> None:
    if sys.platform == WINDOWS_PLATFORM_TAG:
        print(WINDOWS_SKIP_LINE)
        return
    print(restore_dev_null())


if __name__ == "__main__":
    main()
