"""Snapshot a checkout's working tree as a commit, for the turn review Stop gate.

A snapshot is a commit built from a copy of the repository's index after
``git add -A``, so untracked files count and the user's own index stays as it
was::

    prompt  ->  working_tree_snapshot(root, None)  ->  A  (parent HEAD)
    stop    ->  working_tree_snapshot(root, A)     ->  B  (parent A)
    turn_changed_paths(root, A, B)                 ->  ["src/service.py"]

Chaining each snapshot onto the last one makes ``A..B`` a single commit that
holds only the edits made between the two calls.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.turn_review_gate_constants import (
    ALL_CHANGED_PATH_ARGUMENTS,
    ALL_INDEX_PATH_ARGUMENTS,
    ALL_SNAPSHOT_IDENTITY_VARIABLES,
    CHANGED_PATH_SEPARATOR,
    GIT_COMMAND_TIMEOUT_SECONDS,
    GIT_OUTPUT_ENCODING,
    GIT_OUTPUT_ERROR_HANDLING,
    GIT_INDEX_FILE_ENVIRONMENT_VARIABLE,
    SNAPSHOT_COMMIT_MESSAGE,
    TEMPORARY_INDEX_FILE_NAME,
)


def _git_output(
    repository_root: Path,
    all_arguments: list[str],
    all_environment_variables: dict[str, str] | None = None,
) -> str | None:
    try:
        completed_process = subprocess.run(
            ["git", *all_arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding=GIT_OUTPUT_ENCODING,
            errors=GIT_OUTPUT_ERROR_HANDLING,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            cwd=str(repository_root),
            env=all_environment_variables,
            creationflags=hidden_window_creation_flags(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed_process.returncode != 0:
        return None
    return completed_process.stdout.rstrip("\n")


def _working_tree_object(repository_root: Path) -> str | None:
    index_path_text = _git_output(repository_root, list(ALL_INDEX_PATH_ARGUMENTS))
    if index_path_text is None:
        return None
    with tempfile.TemporaryDirectory() as index_directory:
        temporary_index = Path(index_directory) / TEMPORARY_INDEX_FILE_NAME
        try:
            shutil.copyfile(repository_root / index_path_text, temporary_index)
        except OSError:
            return None
        all_index_environment_variables = {
            **os.environ,
            GIT_INDEX_FILE_ENVIRONMENT_VARIABLE: str(temporary_index),
        }
        if _git_output(repository_root, ["add", "-A"], all_index_environment_variables) is None:
            return None
        return _git_output(repository_root, ["write-tree"], all_index_environment_variables)


def working_tree_snapshot(repository_root: Path, base_commit: str | None) -> str | None:
    """Return a commit that holds the working tree as it is now.

    Args:
        repository_root: The checkout to snapshot.
        base_commit: The previous snapshot, used as the parent. None uses HEAD.

    Returns:
        The snapshot commit, ``base_commit`` itself when the tree has not
        changed since it, or None when git cannot build one.
    """
    tree = _working_tree_object(repository_root)
    if tree is None:
        return None
    if (
        base_commit
        and _git_output(repository_root, ["rev-parse", f"{base_commit}^{{tree}}"]) == tree
    ):
        return base_commit
    parent = base_commit or "HEAD"
    return _git_output(
        repository_root,
        ["commit-tree", tree, "-p", parent, "-m", SNAPSHOT_COMMIT_MESSAGE],
        {**os.environ, **ALL_SNAPSHOT_IDENTITY_VARIABLES},
    )


def turn_changed_paths(repository_root: Path, base_commit: str, turn_commit: str) -> list[str]:
    """Return the repository-relative paths that differ between two snapshots."""
    if base_commit == turn_commit:
        return []
    diff_names = _git_output(
        repository_root, [*ALL_CHANGED_PATH_ARGUMENTS, base_commit, turn_commit]
    )
    return [each for each in (diff_names or "").split(CHANGED_PATH_SEPARATOR) if each]
