#!/usr/bin/env python3
"""PreToolUse hook that keeps every SendUserFile path under the session's working directory.

The desktop file pane resolves a sent file only under the session's root
folder, the ``cwd`` in the hook payload. A file elsewhere, such as a network
share or the session scratchpad, passes SendUserFile's own check and then shows
"Couldn't find this file" to the user::

    SendUserFile {"files": ["<cwd>\\.scratch\\a.md"]}        -> allowed
    SendUserFile {"files": ["Y:\\share\\a.md"]}               -> denied
    SendUserFile {"files": ["<cwd>\\..\\other\\a.md"]}        -> denied
    a relative path                                         -> joined to cwd
    no cwd, no files list, or another tool                  -> allowed

Paths compare case-insensitively with Windows rules when ``cwd`` is a Windows
path, and with POSIX rules otherwise. The deny reason lists each outside file
and names ``<cwd>\\.scratch\\`` as the folder to copy it into.
"""

from __future__ import annotations

import ntpath
import posixpath
import sys
from pathlib import Path
from types import ModuleType

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.context_budget_constants import CWD_KEY
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.send_user_file_worktree_root_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    FILES_INPUT_KEY,
    GATE_EVENT_NAME,
    OFFENDING_INPUT_SEPARATOR,
    OUTSIDE_ROOT_HEADER,
    SCRATCH_FOLDER_INSTRUCTION,
    SCRATCH_FOLDER_NAME,
    SEND_USER_FILE_TOOL_NAME,
    WINDOWS_PATH_PATTERN,
)
from hooks_constants.spawn_readiness_hook_constants import TOOL_INPUT_KEY, TOOL_NAME_KEY


def _path_rules_for(working_directory: str) -> ModuleType:
    return ntpath if WINDOWS_PATH_PATTERN.match(working_directory) else posixpath


def is_under_working_directory(file_path: str, working_directory: str) -> bool:
    """Return True when the file path names the working directory or a path inside it.

    >>> is_under_working_directory("C:\\\\wt\\\\.scratch\\\\a.md", "c:/WT")
    True
    >>> is_under_working_directory("Y:\\\\share\\\\a.md", "C:\\\\wt")
    False

    Args:
        file_path: One path from the SendUserFile ``files`` list.
        working_directory: The session's ``cwd`` from the hook payload.

    Returns:
        True for the root itself or a path under it after joining and normalizing.
    """
    path_rules = _path_rules_for(working_directory)
    root = path_rules.normcase(path_rules.normpath(working_directory))
    candidate = path_rules.normcase(
        path_rules.normpath(path_rules.join(working_directory, file_path))
    )
    if candidate == root:
        return True
    return candidate.startswith(root.rstrip(path_rules.sep) + path_rules.sep)


def outside_files(tool_input: object, working_directory: str) -> list[str]:
    """Return each SendUserFile path that sits outside the working directory.

    Args:
        tool_input: The SendUserFile tool input.
        working_directory: The session's ``cwd`` from the hook payload.

    Returns:
        The outside paths in call order, or an empty list when no files list is present.
    """
    all_files = tool_input.get(FILES_INPUT_KEY) if isinstance(tool_input, dict) else None
    if not isinstance(all_files, list):
        return []
    return [
        each_file
        for each_file in all_files
        if isinstance(each_file, str)
        and not is_under_working_directory(each_file, working_directory)
    ]


def format_block_reason(all_outside_files: list[str], working_directory: str) -> str:
    """Return the deny message that lists the outside files and the folder to copy them into.

    Args:
        all_outside_files: Paths outside the working directory.
        working_directory: The session's ``cwd`` from the hook payload.

    Returns:
        The message the session reads when the call is denied.
    """
    path_rules = _path_rules_for(working_directory)
    scratch_folder = path_rules.join(working_directory, SCRATCH_FOLDER_NAME) + path_rules.sep
    file_lines = "".join(f"- {each_file}\n" for each_file in all_outside_files)
    return (
        OUTSIDE_ROOT_HEADER.format(cwd=working_directory)
        + file_lines
        + SCRATCH_FOLDER_INSTRUCTION.format(scratch_folder=scratch_folder)
    )


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None or hook_input.get(TOOL_NAME_KEY) != SEND_USER_FILE_TOOL_NAME:
        return ALLOW_EXIT_CODE
    working_directory = hook_input.get(CWD_KEY)
    if not isinstance(working_directory, str) or not working_directory:
        return ALLOW_EXIT_CODE
    all_outside_files = outside_files(hook_input.get(TOOL_INPUT_KEY), working_directory)
    if not all_outside_files:
        return ALLOW_EXIT_CODE
    block_reason = format_block_reason(all_outside_files, working_directory)
    log_hook_block(
        Path(__file__).name,
        GATE_EVENT_NAME,
        block_reason,
        tool_name=SEND_USER_FILE_TOOL_NAME,
        offending_input_preview=OFFENDING_INPUT_SEPARATOR.join(all_outside_files),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
