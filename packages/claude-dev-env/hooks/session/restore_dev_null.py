#!/usr/bin/env python3
"""SessionStart hook — restores /dev/null when a command has replaced it.

A command that removes or overwrites ``/dev/null`` leaves a regular file at that
path, so later shell redirects such as ``2>/dev/null`` write into that file.
At session start this hook checks the path. When it is not the character device
1:3, the hook removes the entry and recreates it with
``mknod -m 666 /dev/null c 1 3``. A healthy path is left unchanged. Only Linux
maps /dev/null to 1:3, so other platforms skip the check.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.restore_dev_null_constants import (
    DEV_NULL_MAJOR,
    DEV_NULL_MINOR,
    DEV_NULL_MODE,
    DEV_NULL_PATH,
    LINUX_PLATFORM_TAG,
    MKNOD_TIMEOUT_SECONDS,
    NON_LINUX_SKIP_LINE,
)


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
    if sys.platform != LINUX_PLATFORM_TAG:
        sys.stdout.write(NON_LINUX_SKIP_LINE + "\n")
        return
    sys.stdout.write(restore_dev_null() + "\n")


if __name__ == "__main__":
    main()
