"""Find a skill invocation after the last transcript compaction, or one with a given first argument anywhere.

It also lists the tool calls made since the last user prompt, each with whether its result came back without an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Iterator
from typing import NamedTuple

from hooks_constants.transcript_skill_scan_constants import (
    ASSISTANT_ENTRY_TYPE,
    COMMAND_ARGUMENTS_PATTERN,
    COMPACT_BOUNDARY_SUBTYPE,
    IS_ERROR_FIELD,
    META_ENTRY_FIELD,
    SKILL_TOOL_NAME,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_FIELD,
    USER_ENTRY_TYPE,
)


class TranscriptToolCall(NamedTuple):
    """One tool call in a transcript: its name, its input, and whether its result came back without an error."""

    name: str
    tool_input: dict[str, object]
    succeeded: bool


def _user_command_text(all_entry_fields: dict[str, object]) -> str | None:
    message = all_entry_fields.get("message")
    if all_entry_fields.get("type") != USER_ENTRY_TYPE or not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _named_skill_inputs(
    all_entry_fields: dict[str, object],
    skill_names: Collection[str],
    accepts_plugin_prefix: bool = True,
) -> Iterator[dict[str, object]]:
    for each_block in _named_skill_blocks(all_entry_fields, skill_names, accepts_plugin_prefix):
        skill_input = each_block["input"]
        if isinstance(skill_input, dict):
            yield skill_input


def _named_skill_blocks(
    all_entry_fields: dict[str, object],
    skill_names: Collection[str],
    accepts_plugin_prefix: bool = True,
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
            invoked_name == name or (accepts_plugin_prefix and invoked_name.endswith(":" + name))
            for name in skill_names
        ):
            yield each_block


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
    return isinstance(text, str) and [
        each_word.casefold() for each_word in text.split()[:1]
    ] == [argument_word.casefold()]


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
        for each_input in _named_skill_inputs(
            all_entry_fields, skill_names, accepts_plugin_prefix=False
        )
    )


def _parsed_entry(each_line: str) -> dict[str, object] | None:
    try:
        all_entry_fields = json.loads(each_line)
    except json.JSONDecodeError:
        return None
    return all_entry_fields if isinstance(all_entry_fields, dict) else None


def _relevant_entry(each_line: str, skill_names: Collection[str]) -> dict[str, object] | None:
    if not any(name in each_line for name in skill_names) and COMPACT_BOUNDARY_SUBTYPE not in each_line:
        return None
    return _parsed_entry(each_line)


def skill_invocation_status(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> tuple[bool, bool]:
    """Report whether the skill was ever invoked and whether it is loaded now.

    ::

        Skill call                                   -> (True, True)
        Skill call, compact boundary                 -> (True, False)
        Skill call, its tool result with is_error    -> (False, False)
        Skill call refused, Skill call               -> (True, True)

    A Skill call counts until its tool result comes back with ``is_error``,
    so a refused load leaves the skill unloaded. A call whose result has not
    arrived yet still counts.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.

    Returns:
        Whether any entry invoked the skill, and whether an invocation follows
        the last compact boundary.
    """
    all_invoked_calls: set[object] = set()
    all_loaded_calls: set[object] = set()
    was_invoked_by_command = False
    is_loaded_by_command = False
    for each_line in all_transcript_lines:
        all_entry_fields = _relevant_entry(each_line, skill_names) or _result_entry(
            each_line, all_invoked_calls
        )
        if all_entry_fields is None:
            continue
        if all_entry_fields.get("subtype") == COMPACT_BOUNDARY_SUBTYPE:
            all_loaded_calls = set()
            is_loaded_by_command = False
            continue
        all_refused_calls = _errored_result_ids(all_entry_fields)
        all_invoked_calls -= all_refused_calls
        all_loaded_calls -= all_refused_calls
        command_text = _user_command_text(all_entry_fields)
        if command_text is not None:
            if any(marker in command_text for marker in slash_command_markers):
                was_invoked_by_command = is_loaded_by_command = True
            continue
        all_new_calls = {
            each_block.get("id") or object()
            for each_block in _named_skill_blocks(all_entry_fields, skill_names)
        }
        all_invoked_calls |= all_new_calls
        all_loaded_calls |= all_new_calls
    return (
        was_invoked_by_command or bool(all_invoked_calls),
        is_loaded_by_command or bool(all_loaded_calls),
    )


def _result_entry(each_line: str, all_call_ids: Collection[object]) -> dict[str, object] | None:
    if not any(isinstance(each_id, str) and each_id in each_line for each_id in all_call_ids):
        return None
    return _parsed_entry(each_line)


def is_skill_loaded_after_last_compaction(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    """Return whether a matching invocation follows the last compact boundary.

    A Skill call whose tool result came back with ``is_error`` does not count.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.
    """
    return skill_invocation_status(all_transcript_lines, skill_names, slash_command_markers)[1]


def _is_user_prompt(all_entry_fields: dict[str, object]) -> bool:
    message = all_entry_fields.get("message")
    if all_entry_fields.get("type") != USER_ENTRY_TYPE or all_entry_fields.get(META_ENTRY_FIELD):
        return False
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(each_block, dict) and each_block.get("type") == TOOL_RESULT_BLOCK_TYPE
        for each_block in content
    )


def is_skill_loaded_since_last_prompt(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    """Return whether a matching invocation follows the last user prompt and compact boundary.

    ::

        prompt, Skill verify, tool result, skill body   -> True
        prompt, Skill verify, tool result with is_error -> False
        prompt, Skill verify, no tool result yet        -> False
        prompt, Skill verify, prompt                    -> False
        prompt carrying the /verify command marker      -> True
        prompt with the marker, compact boundary        -> False

    A Skill call counts once its tool result comes back without an error, so a
    refused load leaves the skill unloaded. A tool result and a meta entry, such
    as the skill body, leave the turn open.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.
    """
    loaded = False
    all_pending_ids: set[object] = set()
    for each_line in all_transcript_lines:
        all_entry_fields = _parsed_entry(each_line)
        if all_entry_fields is None:
            continue
        if all_entry_fields.get("subtype") == COMPACT_BOUNDARY_SUBTYPE or _is_user_prompt(all_entry_fields):
            loaded = False
            all_pending_ids = set()
        command_text = _user_command_text(all_entry_fields)
        if command_text is not None:
            loaded = loaded or any(marker in command_text for marker in slash_command_markers)
        all_pending_ids.update(
            each_block["id"]
            for each_block in _named_skill_blocks(all_entry_fields, skill_names)
            if each_block.get("id") is not None
        )
        loaded = loaded or bool(all_pending_ids & _succeeded_result_ids(all_entry_fields))
    return loaded


def invokes_skill_with_argument(
    all_transcript_lines: Iterable[str],
    skill_names: Collection[str],
    argument_word: str,
    command_marker: str,
) -> bool:
    """Return whether any entry invoked the skill with ``argument_word`` as its first argument.

    ::

        Skill claude-api, args "build-eval extra"            -> True
        Skill claude-api, args "Build-Eval"                   -> True
        Skill plugin:claude-api, args "build-eval"            -> False
        Skill claude-api, args "migrate"                      -> False
        user "/claude-api" command, command-args "build-eval" -> True

    An invocation stays counted after a later compact boundary. A Skill tool
    call must name the skill exactly, so a same-named skill from another
    plugin does not count. A user command counts by its ``command_marker``
    alone. The argument word matches without regard to case.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        skill_names: Skill tool names, matched exactly.
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


def _content_blocks(all_entry_fields: dict[str, object], entry_type: str) -> list[dict[str, object]]:
    message = all_entry_fields.get("message")
    if all_entry_fields.get("type") != entry_type or not isinstance(message, dict):
        return []
    content = message.get("content")
    return [each_block for each_block in (content if isinstance(content, list) else []) if isinstance(each_block, dict)]


def _tool_use_calls(all_entry_fields: dict[str, object]) -> list[tuple[object, str, dict[str, object]]]:
    all_tool_use_calls: list[tuple[object, str, dict[str, object]]] = []
    for each_block in _content_blocks(all_entry_fields, ASSISTANT_ENTRY_TYPE):
        tool_name = each_block.get("name")
        tool_input = each_block.get("input")
        if each_block.get("type") == TOOL_USE_BLOCK_TYPE and isinstance(tool_name, str):
            all_tool_use_calls.append((each_block.get("id"), tool_name, tool_input if isinstance(tool_input, dict) else {}))
    return all_tool_use_calls


def _errored_result_ids(all_entry_fields: dict[str, object]) -> set[object]:
    return {
        each_block.get(TOOL_USE_ID_FIELD)
        for each_block in _content_blocks(all_entry_fields, USER_ENTRY_TYPE)
        if each_block.get("type") == TOOL_RESULT_BLOCK_TYPE and each_block.get(IS_ERROR_FIELD) is True
    }


def _succeeded_result_ids(all_entry_fields: dict[str, object]) -> set[object]:
    return {
        each_block.get(TOOL_USE_ID_FIELD)
        for each_block in _content_blocks(all_entry_fields, USER_ENTRY_TYPE)
        if each_block.get("type") == TOOL_RESULT_BLOCK_TYPE and each_block.get(IS_ERROR_FIELD) is not True
    }


def tool_calls_since_last_prompt(all_transcript_lines: Iterable[str]) -> list[TranscriptToolCall]:
    """Return the tool calls after the last user prompt, in order, each marked by whether it succeeded.

    ::

        prompt, reply call, its result without an error  -> [reply succeeded]
        prompt, reply call, its result with is_error     -> [reply failed]
        prompt, resolve call with no result yet          -> [resolve failed]
        reply call and result, then a new prompt         -> []

    A hook that denies a call leaves an errored result, so a denied call does
    not count as a success. A tool result leaves the turn open.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
    """
    all_calls: list[tuple[object, str, dict[str, object]]] = []
    all_succeeded_ids: set[object] = set()
    all_entries = (each_entry for each_entry in map(_parsed_entry, all_transcript_lines) if each_entry is not None)
    for each_entry_fields in all_entries:
        if _is_user_prompt(each_entry_fields):
            all_calls, all_succeeded_ids = [], set()
            continue
        all_calls.extend(_tool_use_calls(each_entry_fields))
        all_succeeded_ids.update(_succeeded_result_ids(each_entry_fields))
    return [
        TranscriptToolCall(each_name, each_input, each_id is not None and each_id in all_succeeded_ids)
        for each_id, each_name, each_input in all_calls
    ]
