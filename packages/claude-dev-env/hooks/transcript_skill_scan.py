"""Find a skill invocation after the last transcript compaction."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable

from hooks_constants.transcript_skill_scan_constants import (
    ASSISTANT_ENTRY_TYPE,
    COMPACT_BOUNDARY_SUBTYPE,
    SKILL_TOOL_NAME,
    TOOL_USE_BLOCK_TYPE,
    USER_ENTRY_TYPE,
)


def _invokes_skill(
    all_entry_fields: dict[str, object],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    message = all_entry_fields.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if all_entry_fields.get("type") == USER_ENTRY_TYPE and isinstance(content, str):
        return any(marker in content for marker in slash_command_markers)
    if all_entry_fields.get("type") != ASSISTANT_ENTRY_TYPE or not isinstance(content, list):
        return False
    for each_block in content:
        if not isinstance(each_block, dict) or each_block.get("type") != TOOL_USE_BLOCK_TYPE:
            continue
        if each_block.get("name") != SKILL_TOOL_NAME or not isinstance(each_block.get("input"), dict):
            continue
        invoked_name = each_block["input"].get("skill")
        if isinstance(invoked_name, str) and any(
            invoked_name == name or invoked_name.endswith(":" + name) for name in skill_names
        ):
            return True
    return False


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
