"""Names and messages for the send_user_file_worktree_root_gate PreToolUse hook."""

from __future__ import annotations

import re

__all__ = [
    "ALLOW_EXIT_CODE",
    "BLOCK_EXIT_CODE",
    "FILES_INPUT_KEY",
    "GATE_EVENT_NAME",
    "OFFENDING_INPUT_SEPARATOR",
    "OUTSIDE_ROOT_HEADER",
    "SCRATCH_FOLDER_NAME",
    "SCRATCH_FOLDER_INSTRUCTION",
    "SEND_USER_FILE_TOOL_NAME",
    "WINDOWS_PATH_PATTERN",
]

ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
SEND_USER_FILE_TOOL_NAME = "SendUserFile"
FILES_INPUT_KEY = "files"
GATE_EVENT_NAME = "PreToolUse"
OFFENDING_INPUT_SEPARATOR = ", "
SCRATCH_FOLDER_NAME = ".scratch"
WINDOWS_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:|\\\\)")
OUTSIDE_ROOT_HEADER = (
    "The desktop file pane opens a sent file only when it sits under this session's"
    " working directory, {cwd}. These files are outside it, so the user sees"
    ' "Couldn\'t find this file":\n'
)
SCRATCH_FOLDER_INSTRUCTION = (
    "\nCopy each file into {scratch_folder} and call SendUserFile with the copied paths."
    " If git does not ignore that folder, add .scratch/ to .git/info/exclude first."
)
