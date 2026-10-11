"""Directory link helper shared by tests that follow a linked folder."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def create_directory_link(*, from_link: Path, to_target: Path) -> None:
    """Point a new directory link at a target folder.

    Windows gets a junction, which needs no extra rights, so a failure there
    fails the test. Other systems get a symlink, and a host that refuses it
    skips the calling test.

    Args:
        from_link: Where the new link goes.
        to_target: The folder the link points at.
    """
    if sys.platform.startswith("win32"):
        importlib.import_module("_winapi").CreateJunction(str(to_target), str(from_link))
        return
    try:
        os.symlink(to_target, from_link, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not available")
