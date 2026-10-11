"""Directory link helper shared by tests that follow a linked folder."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def create_directory_link(*, from_link: Path, to_target: Path) -> None:
    """Point a new directory link at a target folder, or skip the test.

    Windows gets a junction and other systems get a symlink. A host that
    refuses the link skips the calling test.

    Args:
        from_link: Where the new link goes.
        to_target: The folder the link points at.
    """
    try:
        if sys.platform.startswith("win32"):
            importlib.import_module("_winapi").CreateJunction(
                str(to_target), str(from_link)
            )
        else:
            os.symlink(to_target, from_link, target_is_directory=True)
    except OSError:
        pytest.skip("directory link creation is not available")
