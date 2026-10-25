#!/usr/bin/env python3
"""Search starts for the transcript root search gate.

A search start is the path a search begins at and whether the search recurses
from it. This module decides whether a start walks every project folder under
a Claude transcript root, reads the start of a Grep or Glob tool call, and
holds the option helpers the shell readers share.
``blocking/transcript_root_shell_starts.py`` and
``blocking/transcript_root_powershell_starts.py`` read the starts of a shell
command, and ``blocking/transcript_root_search_gate.py`` denies the call when
one walks a root.
"""

from __future__ import annotations

import collections
import posixpath
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants import transcript_root_search_gate_constants as search_rules
    from hooks_constants.pytest_invocation import unquoted_token
except ImportError as import_error:
    raise ImportError(
        "The transcript root gate helpers cannot import their dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


OptionValue = tuple[str, str]


@dataclass(frozen=True)
class SearchStart:
    """One place a search begins.

    Attributes:
        path_text: The path or glob the search starts from, as the call names it.
        is_recursive: True when the search descends below the path on its own.
    """

    path_text: str
    is_recursive: bool


def normalized_path(path_text: str) -> str:
    """Return the path with quotes removed, forward slashes, and ``.`` and ``..`` folded.

    ::

        '"C:\\\\h\\\\.claude\\\\projects\\\\"'   -> "C:/h/.claude/projects"
        "~/.claude/projects/C--x/../"          -> "~/.claude/projects"

    Args:
        path_text: A path token, possibly quoted or with backslashes.
    """
    forward_slash_path = unquoted_token(path_text.strip()).replace(
        search_rules.WINDOWS_PATH_SEPARATOR, search_rules.PATH_SEPARATOR
    )
    if not forward_slash_path:
        return forward_slash_path
    return posixpath.normpath(forward_slash_path)


def joined_path(base_directory: str, path_text: str) -> str:
    """Return the path read from the base directory, or the path itself when it is absolute.

    Args:
        base_directory: The directory a relative path resolves from, or empty when unknown.
        path_text: The path a command or tool call names.
    """
    bare_path = unquoted_token(path_text.strip())
    if not base_directory or search_rules.ABSOLUTE_PATH_PATTERN.match(bare_path):
        return bare_path
    return normalized_path(base_directory) + search_rules.PATH_SEPARATOR + bare_path


def is_option(token: str) -> bool:
    """Return True for a token that starts with ``-`` and holds more than the dash."""
    bare_token = unquoted_token(token)
    return len(bare_token) > 1 and bare_token.startswith(search_rules.OPTION_PREFIX)


def next_value(all_remaining: collections.deque[str]) -> str:
    """Take the next token off the queue, unquoted, or empty when none is left."""
    return unquoted_token(all_remaining.popleft()) if all_remaining else ""


def is_recursive_unless_shallow(all_depth_values: list[str], is_recursive_otherwise: bool) -> bool:
    """Return whether a search recurses; the last depth value decides when one is given."""
    if all_depth_values:
        return all_depth_values[-1] not in search_rules.ALL_SHALLOW_DEPTH_VALUES
    return is_recursive_otherwise


def starts_or_current_directory(all_paths: list[str], is_recursive: bool) -> list[SearchStart]:
    """Return one start per path, or one at the current directory when no path is given."""
    return [
        SearchStart(each_path, is_recursive)
        for each_path in all_paths or [search_rules.CURRENT_DIRECTORY]
    ]


def _walks_every_project_folder(all_segments_below_root: list[str], is_recursive: bool) -> bool:
    if not all_segments_below_root:
        return is_recursive
    first_segment, *all_deeper_segments = all_segments_below_root
    if search_rules.WILDCARD_ONLY_SEGMENT_PATTERN.fullmatch(first_segment) is None:
        return False
    return is_recursive or bool(all_deeper_segments)


def walked_transcript_root(search_start: SearchStart) -> str | None:
    """Return the transcript root a search start walks, or None when it stays scoped.

    ::

        SearchStart("~/.claude/projects", True)              -> "~/.claude/projects"
        SearchStart("~/.claude/projects", False)             -> None
        SearchStart("~/.claude/projects/*/*.jsonl", False)   -> "~/.claude/projects"
        SearchStart("~/.claude/projects/*01WU*", False)      -> None
        SearchStart("~/.claude/projects/C--repo", True)      -> None

    Args:
        search_start: The path the search starts from and whether it recurses.
    """
    start_path = normalized_path(search_start.path_text)
    root_match = search_rules.TRANSCRIPT_ROOT_PATTERN.search(start_path)
    if root_match is None:
        return None
    all_segments_below_root = [
        each_segment
        for each_segment in start_path[root_match.end() :].split(search_rules.PATH_SEPARATOR)
        if each_segment
    ]
    if not _walks_every_project_folder(all_segments_below_root, search_start.is_recursive):
        return None
    return start_path[: root_match.end()]


def file_search_tool_start(
    tool_name: str, all_tool_input: dict[str, object], cwd: str
) -> SearchStart:
    """Return where a Grep or Glob tool call starts its search.

    Grep always recurses from its path. Glob reads its pattern below its path,
    or alone when the pattern is absolute, and recurses when the pattern holds
    ``**``. A relative path resolves from the session working directory.

    Args:
        tool_name: ``Grep`` or ``Glob``.
        all_tool_input: The tool call's input.
        cwd: The session working directory, used when the call names no path.
    """
    raw_path = all_tool_input.get(search_rules.TOOL_INPUT_PATH_KEY)
    base_path = joined_path(cwd, raw_path) if isinstance(raw_path, str) and raw_path else cwd
    if tool_name != search_rules.GLOB_TOOL_NAME:
        return SearchStart(base_path, True)
    raw_pattern = all_tool_input.get(search_rules.TOOL_INPUT_PATTERN_KEY)
    pattern = raw_pattern if isinstance(raw_pattern, str) else ""
    return SearchStart(
        joined_path(base_path, pattern), search_rules.RECURSIVE_GLOB_SEGMENT in pattern
    )
