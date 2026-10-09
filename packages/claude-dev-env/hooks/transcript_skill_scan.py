"""Find a skill invocation after the last transcript compaction, or one with a given first argument anywhere."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Iterator

from hooks_constants.transcript_skill_scan_constants import (
    ASSISTANT_ENTRY_TYPE,
    COMMAND_ARGUMENTS_PATTERN,
    COMPACT_BOUNDARY_SUBTYPE,
    SKILL_TOOL_NAME,
    TOOL_USE_BLOCK_TYPE,
    USER_ENTRY_TYPE,
)


def _user_command_text(all_entry_fields: dict[str, object]) -> str | None:
    message = all_entry_fields.get("message")
    if all_entry_fields.get("type") != USER_ENTRY_TYPE or not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _named_skill_inputs(
    all_entry_fields: dict[str, object], skill_names: Collection[str]
) -> Iterator[dict[str, object]]:
    message = all_entry_fields.get("message")
    if all_entry_fields.get("type") != ASSISTANT_ENTRY_TYPE or not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for each_block in content:
        if not isinstance(each_block, dict) or each_block.get("type") != TOOL_USE_BLOCK_TYPE:
            continue
        if each_block.get("name") != SKILL_TOOL_NAME or not isinstance(each_block.get("input"), dict):
            continue
        invoked_name = each_block["input"].get("skill")
        if isinstance(invoked_name, str) and any(
            invoked_name == name or invoked_name.endswith(":" + name) for name in skill_names
        ):
            yield each_block["input"]


def _invokes_skill(
    all_entry_fields: dict[str, object],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    command_text = _user_command_text(all_entry_fields)
    if command_text is not None:
        return any(marker in command_text for marker in slash_command_markers)
    return next(_named_skill_inputs(all_entry_fields, skill_names), None) is not None


def _first_word_is(text: object, argument_word: str) -> bool:
    return isinstance(text, str) and text.split()[:1] == [argument_word]


def _invokes_skill_with_argument(
    all_entry_fields: dict[str, object],
    skill_names: Collection[str],
    argument_word: str,
    command_marker: str,
) -> bool:
    command_text = _user_command_text(all_entry_fields)
    if command_text is not None:
        command_arguments = re.search(COMMAND_ARGUMENTS_PATTERN, command_text, re.DOTALL)
        return (
            command_marker in command_text
            and command_arguments is not None
            and _first_word_is(command_arguments.group(1), argument_word)
        )
    return any(
        _first_word_is(each_input.get("args"), argument_word)
        for each_input in _named_skill_inputs(all_entry_fields, skill_names)
    )


def _relevant_entry(each_line: str, skill_names: Collection[str]) -> dict[str, object] | None:
    if not any(name in each_line for name in skill_names) and COMPACT_BOUNDARY_SUBTYPE not in each_line:
        return None
    try:
        all_entry_fields = json.loads(each_line)
    except json.JSONDecodeError:
        return None
    return all_entry_fields if isinstance(all_entry_fields, dict) else None


def skill_invocation_status(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> tuple[bool, bool]:
    """Report whether the skill was ever invoked and whether it is loaded now.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.

    Returns:
        Whether any entry invoked the skill, and whether an invocation follows
        the last compact boundary.
    """
    was_invoked = False
    loaded = False
    for each_line in all_transcript_lines:
        all_entry_fields = _relevant_entry(each_line, skill_names)
        if all_entry_fields is not None:
            loaded = all_entry_fields.get("subtype") != COMPACT_BOUNDARY_SUBTYPE and (
                loaded or _invokes_skill(all_entry_fields, skill_names, slash_command_markers)
            )
            was_invoked = was_invoked or loaded
    return was_invoked, loaded


def is_skill_loaded_after_last_compaction(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    """Return whether a matching invocation follows the last compact boundary.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.
    """
    return skill_invocation_status(all_transcript_lines, skill_names, slash_command_markers)[1]


def invokes_skill_with_argument(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    argument_word: str,
    command_marker: str,
) -> bool:
    """Return whether any entry invoked the skill with ``argument_word`` as its first argument.

    ::

        Skill claude-api, args "build-eval extra"            -> True
        Skill plugin:claude-api, args "build-eval"            -> True
        Skill claude-api, args "migrate"                      -> False
        user "/claude-api" command, command-args "build-eval" -> True

    An invocation stays counted after a later compact boundary.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        argument_word: The first whitespace-separated word the arguments must carry.
        command_marker: The user command tag that names the skill.
    """
    for each_line in all_transcript_lines:
        if not any(name in each_line for name in skill_names):
            continue
        all_entry_fields = _relevant_entry(each_line, skill_names)
        if all_entry_fields and _invokes_skill_with_argument(all_entry_fields, skill_names, argument_word, command_marker):
            return True
    return False
