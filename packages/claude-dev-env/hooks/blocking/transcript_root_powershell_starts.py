#!/usr/bin/env python3
"""PowerShell cmdlet search starts for the transcript root search gate.

Reads the paths and recursion of a ``Get-ChildItem`` or ``Select-String``
call. ``-Path`` and ``-LiteralPath`` values and positional tokens are paths,
split on commas. An option off the switch list takes the next token as its
value, so ``-ErrorAction 0`` never reads as a path. ``-Depth`` decides
recursion when given, ``0`` meaning one level; otherwise ``-Recurse`` does.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from blocking.transcript_root_search_starts import (
        OptionValue,
        SearchStart,
        is_option,
        next_value,
        starts_or_current_directory,
    )
    from hooks_constants import transcript_root_search_gate_constants as search_rules
    from hooks_constants import unscoped_search_blocker_constants as walk_flags
    from hooks_constants.pytest_invocation import unquoted_token
except ImportError as import_error:
    raise ImportError(
        "The transcript_root_powershell_starts module cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _split_path_list(path_text: str) -> list[str]:
    return [
        each_part
        for each_part in unquoted_token(path_text).split(
            search_rules.POWERSHELL_PATH_LIST_SEPARATOR
        )
        if each_part
    ]


def _powershell_arguments(all_arguments: list[str]) -> tuple[list[str], list[OptionValue]]:
    """Return a cmdlet call's paths and options; an option off the switch list takes a value."""
    all_paths: list[str] = []
    all_options: list[OptionValue] = []
    all_remaining = collections.deque(all_arguments)
    while all_remaining:
        bare_token = unquoted_token(all_remaining.popleft())
        if not is_option(bare_token):
            all_paths.extend(_split_path_list(bare_token))
            continue
        option_name, glued_separator, glued_value = bare_token.partition(
            search_rules.POWERSHELL_GLUED_VALUE_SEPARATOR
        )
        option_name = option_name.lower()
        takes_spaced_value = not glued_separator and (
            option_name not in search_rules.ALL_POWERSHELL_SWITCH_OPTIONS
        )
        option_value = next_value(all_remaining) if takes_spaced_value else glued_value
        all_options.append((option_name, unquoted_token(option_value)))
        if option_name in walk_flags.ALL_POWERSHELL_PATH_FLAGS:
            all_paths.extend(_split_path_list(option_value))
    return all_paths, all_options


def _powershell_listing_is_recursive(all_options: list[OptionValue]) -> bool:
    all_depth_values = [
        each_value
        for each_name, each_value in all_options
        if each_name == search_rules.POWERSHELL_DEPTH_OPTION
    ]
    if all_depth_values:
        return all_depth_values[-1] != search_rules.POWERSHELL_NON_RECURSIVE_DEPTH
    return any(
        each_name in walk_flags.ALL_POWERSHELL_RECURSE_FLAGS
        and (not each_value or each_value.lower() in walk_flags.ALL_TRUTHY_RECURSE_COLON_VALUES)
        for each_name, each_value in all_options
    )


def powershell_listing_search_starts(all_arguments: list[str]) -> list[SearchStart]:
    """Return the starts of a ``Get-ChildItem`` call, or of ``ls`` under PowerShell."""
    all_paths, all_options = _powershell_arguments(all_arguments)
    return starts_or_current_directory(all_paths, _powershell_listing_is_recursive(all_options))


def select_string_search_starts(all_arguments: list[str]) -> list[SearchStart]:
    """Return the starts of a ``Select-String`` call, which reads only the paths it names."""
    all_paths, _all_options = _powershell_arguments(all_arguments)
    return [SearchStart(each_path, False) for each_path in all_paths]
