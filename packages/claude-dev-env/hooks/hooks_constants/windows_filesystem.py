"""Shared Windows-safe directory-tree removal for the hooks package.

Windows refuses to delete a file that carries the ReadOnly attribute, which git
sets on pack files and which a test sandbox can leave behind. ``force_rmtree``
clears the attribute and retries each refused removal, so every hook and test
that removes a tree imports this one helper.
"""

from __future__ import annotations

import inspect
import os
import shutil
import stat
from collections.abc import Callable

__all__ = ["force_rmtree"]

_rmtree_supports_onexc = "onexc" in inspect.signature(shutil.rmtree).parameters


def _strip_read_only_and_retry(
    removal_function: Callable[[str], None],
    target_path: str,
    *_unused_exception_info: object,
) -> None:
    try:
        os.chmod(target_path, stat.S_IWRITE)
        removal_function(target_path)
    except OSError:
        pass


def force_rmtree(target_path: str) -> None:
    """Remove a directory tree, clearing the ReadOnly attribute on refused entries.

    Python 3.12 renamed the rmtree error callback to ``onexc``; earlier versions
    accept only ``onerror``. The helper passes whichever keyword the running
    interpreter's ``shutil.rmtree`` accepts.

    Args:
        target_path: The directory tree to remove. A tree that cannot be
            removed, including a missing one, is left as is without raising.
    """
    try:
        if _rmtree_supports_onexc:
            shutil.rmtree(target_path, onexc=_strip_read_only_and_retry)
        else:
            shutil.rmtree(target_path, onerror=_strip_read_only_and_retry)
    except OSError:
        pass
