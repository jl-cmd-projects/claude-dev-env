"""Constants for the instruction-file write warning hook."""

from __future__ import annotations

TOOL_INPUT_KEY: str = "tool_input"
FILE_PATH_KEY: str = "file_path"
CONTEXT_HEADER_TEMPLATE: str = (
    "Instruction budget check for {file_path}. Fix each line before the next write:"
)
CONTEXT_LINE_SEPARATOR: str = "\n"
