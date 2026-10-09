"""Tests for the shared Windows-safe force_rmtree helper."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks_constants import windows_filesystem
from hooks_constants.windows_filesystem import force_rmtree

_original_unlink = os.unlink


def _unlink_refusing_read_only_files(path, *, dir_fd=None):
    file_mode = os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode
    if not file_mode & stat.S_IWRITE:
        raise PermissionError(f"read-only file refused: {path}")
    _original_unlink(path, dir_fd=dir_fd)


@pytest.fixture
def tree_with_read_only_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tree_root = tmp_path / "tree"
    nested_directory = tree_root / "nested"
    nested_directory.mkdir(parents=True)
    read_only_file = nested_directory / "pack.idx"
    read_only_file.write_text("packed", encoding="utf-8")
    os.chmod(read_only_file, stat.S_IREAD)
    monkeypatch.setattr(os, "unlink", _unlink_refusing_read_only_files)
    with pytest.raises(PermissionError):
        os.unlink(read_only_file)
    return tree_root


def test_removes_tree_holding_read_only_file(tree_with_read_only_file: Path) -> None:
    force_rmtree(str(tree_with_read_only_file))
    assert not tree_with_read_only_file.exists()


def test_removes_read_only_file_through_onerror_callback(
    tree_with_read_only_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows_filesystem, "_rmtree_supports_onexc", False)
    force_rmtree(str(tree_with_read_only_file))
    assert not tree_with_read_only_file.exists()


def test_missing_tree_does_not_raise(tmp_path: Path) -> None:
    missing_tree = tmp_path / "absent"
    force_rmtree(str(missing_tree))
    assert not missing_tree.exists()
