"""Find the hooks that nested checkouts declare for one event.

A session directory can hold several checkouts, each with its own settings::

    session directory
    |-- checkout-a/.claude/settings.json   PreToolUse "Bash" -> ./gate.sh
    `-- checkout-b/.claude/settings.json   SessionStart      -> ./start.sh

For a PreToolUse call on ``Bash`` this module returns one ``NestedHook`` for
``./gate.sh`` in checkout-a. The forwarder in ``nested_project_hooks`` runs it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.nested_project_hooks_constants import (
    ALL_MATCH_EVERYTHING_MATCHERS,
    CHECKOUT_MARKER_NAME,
    COMMAND_HOOK_TYPE,
    COMMAND_KEY,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    HOOK_TYPE_KEY,
    HOOKS_KEY,
    MATCHER_KEY,
    SETTINGS_DIRECTORY_NAME,
    SETTINGS_ENCODING,
    SETTINGS_FILE_NAME,
    TIMEOUT_KEY,
)


@dataclass(frozen=True)
class NestedHook:
    """One command hook a nested checkout declares for the current event."""

    project_directory: Path
    command: str
    timeout_seconds: float


def _settings_path(directory: Path) -> Path:
    return directory / SETTINGS_DIRECTORY_NAME / SETTINGS_FILE_NAME


def find_nested_projects(session_directory: Path) -> list[Path]:
    """Return the child checkouts whose project hooks Claude Code skipped.

    Args:
        session_directory: The directory the session started in.

    Returns:
        Each immediate child holding both a ``.git`` entry and a
        ``.claude/settings.json`` file, sorted by name. Empty when the
        session directory is a checkout or has settings of its own.
    """
    if (session_directory / CHECKOUT_MARKER_NAME).exists():
        return []
    if _settings_path(session_directory).is_file():
        return []
    try:
        all_children = sorted(session_directory.iterdir())
    except OSError:
        return []
    return [
        each_child
        for each_child in all_children
        if each_child.is_dir()
        and (each_child / CHECKOUT_MARKER_NAME).exists()
        and _settings_path(each_child).is_file()
    ]


def _read_hook_groups(project_directory: Path, event_name: str) -> list[object]:
    try:
        settings_text = _settings_path(project_directory).read_text(encoding=SETTINGS_ENCODING)
        settings = json.loads(settings_text)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(settings, dict):
        return []
    hooks_by_event = settings.get(HOOKS_KEY)
    if not isinstance(hooks_by_event, dict):
        return []
    all_groups = hooks_by_event.get(event_name)
    if not isinstance(all_groups, list):
        return []
    return all_groups


def matcher_selects(matcher: object, match_target: str) -> bool:
    """Report whether a settings matcher selects this event's target.

    Args:
        matcher: The ``matcher`` value of one hook group, possibly absent.
        match_target: The tool name for PreToolUse, the start source for
            SessionStart.

    Returns:
        True for an absent, empty, or ``*`` matcher, and for a matcher whose
        pattern matches the whole target. An invalid pattern matches only
        its exact text.
    """
    if matcher is None:
        return True
    if not isinstance(matcher, str):
        return False
    if matcher in ALL_MATCH_EVERYTHING_MATCHERS:
        return True
    try:
        return re.fullmatch(matcher, match_target) is not None
    except re.error:
        return matcher == match_target


def _command_hook(project_directory: Path, hook_fields: object) -> NestedHook | None:
    if not isinstance(hook_fields, dict):
        return None
    if hook_fields.get(HOOK_TYPE_KEY) != COMMAND_HOOK_TYPE:
        return None
    command = hook_fields.get(COMMAND_KEY)
    if not isinstance(command, str) or not command.strip():
        return None
    timeout_value = hook_fields.get(TIMEOUT_KEY)
    timeout_seconds = DEFAULT_HOOK_TIMEOUT_SECONDS
    if isinstance(timeout_value, (int, float)) and timeout_value > 0:
        timeout_seconds = float(timeout_value)
    return NestedHook(project_directory, command, timeout_seconds)


def _selected_hook_entries(
    project_directory: Path, event_name: str, match_target: str
) -> list[object]:
    all_hook_entries: list[object] = []
    for each_group in _read_hook_groups(project_directory, event_name):
        if not isinstance(each_group, dict):
            continue
        if not matcher_selects(each_group.get(MATCHER_KEY), match_target):
            continue
        all_group_hooks = each_group.get(HOOKS_KEY)
        if isinstance(all_group_hooks, list):
            all_hook_entries.extend(all_group_hooks)
    return all_hook_entries


def collect_nested_hooks(
    session_directory: Path, event_name: str, match_target: str
) -> list[NestedHook]:
    """Return every nested command hook that this event selects, in order.

    Args:
        session_directory: The directory the session started in.
        event_name: The hook event being handled.
        match_target: The value the event's matchers compare against.

    Returns:
        The selected command hooks, checkout by checkout in name order and
        in declaration order inside each checkout.
    """
    all_candidates = (
        _command_hook(each_project, each_entry)
        for each_project in find_nested_projects(session_directory)
        for each_entry in _selected_hook_entries(each_project, event_name, match_target)
    )
    return [each_candidate for each_candidate in all_candidates if each_candidate is not None]
