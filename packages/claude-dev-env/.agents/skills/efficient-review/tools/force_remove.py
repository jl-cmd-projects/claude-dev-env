"""Remove a temporary directory, including a read-only file."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path


def force_remove_tree(path: Path) -> None:
    """Delete one directory tree.

    Args:
        path: The directory to delete.
    """
    shutil.rmtree(path, onerror=_retry_writable)


def _retry_writable(
    remove_entry: Callable[[str], object],
    failed_path: str,
    _error: object,
) -> None:
    os.chmod(failed_path, stat.S_IWRITE)
    remove_entry(failed_path)
