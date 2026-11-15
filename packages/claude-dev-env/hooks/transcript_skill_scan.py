"""Find a skill invocation after the last transcript compaction, or one with a given first argument anywhere.

A reader gives a large transcript's lines newest first, so a recent invocation answers without reading the whole file.

It also lists the tool calls made since the last user prompt, each with whether its result came back without an error.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable, Collection, Iterable, Iterator
from io import SEEK_END
from typing import BinaryIO, NamedTuple

from hooks_constants.transcript_skill_scan_constants import (
    ALL_LINE_BREAK_BYTES,
    ASSISTANT_ENTRY_TYPE,
    CARRIAGE_RETURN_BYTE,
    COMMAND_ARGUMENTS_PATTERN,
    COMPACT_BOUNDARY_SUBTYPE,
    FORWARD_COPY_BYTE_CAP,
    IS_ERROR_FIELD,
    META_ENTRY_FIELD,
    NEWLINE_BYTE,
    ORIGIN_FIELD,
    ORIGIN_KIND_FIELD,
    RUN_IN_BACKGROUND_INPUT_KEY,
    SKILL_TOOL_NAME,
    TASK_NOTIFICATION_ORIGIN_KIND,
    TASK_NOTIFICATION_SUCCESS_PATTERN,
    TASK_NOTIFICATION_TOOL_USE_ID_PATTERN,
    TOOL_RESULT_BLOCK_TYPE,
    TRANSCRIPT_BLOCK_BYTES,
    TRANSCRIPT_LINE_BYTE_CAP,
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


def is_skill_loaded_after_last_compaction_newest_first(
    all_lines_newest_first: Iterable[str],
    skill_names: Collection[str],
    slash_command_markers: Collection[str],
) -> bool:
    """Return whether a matching invocation follows the last compact boundary, reading the newest line first.

    ::

        newest first: load, ..., compact boundary   -> True
        newest first: compact boundary, ..., load   -> False
        no load and no compact boundary             -> False

    The first load or compact boundary met decides. The answer equals
    ``is_skill_loaded_after_last_compaction`` on the same lines in file order.

    Args:
        all_lines_newest_first: JSON transcript entries, one per line, newest first.
        skill_names: Accepted skill names, with plugin prefixes accepted.
        slash_command_markers: Accepted user command tags.
    """
    for each_line in all_lines_newest_first:
        all_entry_fields = _relevant_entry(each_line, skill_names)
        if all_entry_fields is None:
            continue
        if all_entry_fields.get("subtype") == COMPACT_BOUNDARY_SUBTYPE:
            return False
        if _invokes_skill(all_entry_fields, skill_names, slash_command_markers):
            return True
    return False


def _always_reads() -> bool:
    return True


def _notes_nothing() -> None:
    return None


class ScanCaps(NamedTuple):
    """The byte caps a newest-first read holds to, and what it calls when one is passed.

    ::

        a line over line_byte_cap                      -> the read stops; on_cap_passed runs once
        a copied stream over forward_copy_byte_cap     -> no lines; on_cap_passed runs once
    """

    line_byte_cap: int = TRANSCRIPT_LINE_BYTE_CAP
    forward_copy_byte_cap: int = FORWARD_COPY_BYTE_CAP
    on_cap_passed: Callable[[], None] = _notes_nothing


def _block_ending_at(
    transcript: BinaryIO, end: int, block_size: int
) -> tuple[int, bytes]:
    start = max(0, end - block_size)
    transcript.seek(start)
    block = transcript.read(end - start)
    if start > 0 and block.startswith(NEWLINE_BYTE):
        transcript.seek(start - 1)
        if transcript.read(1) == CARRIAGE_RETURN_BYTE:
            return start - 1, CARRIAGE_RETURN_BYTE + block
    return start, block


def _blocks_newest_first(
    transcript: BinaryIO, block_size: int, keeps_reading: Callable[[], bool]
) -> Iterator[tuple[int, bytes]]:
    end = transcript.seek(0, SEEK_END)
    while end > 0 and keeps_reading():
        end, block = _block_ending_at(transcript, end, block_size)
        yield end, block


def _block_pieces(block: bytes) -> list[bytes]:
    all_pieces = block.splitlines()
    if block.endswith(ALL_LINE_BREAK_BYTES):
        all_pieces.append(b"")
    return all_pieces


def _complete_lines(
    all_pieces: list[bytes], all_newer_parts: list[bytes], is_file_end: bool
) -> list[bytes]:
    newest_line = all_pieces[-1] + b"".join(reversed(all_newer_parts))
    all_older_lines = list(reversed(all_pieces[1:-1]))
    return (
        [newest_line, *all_older_lines]
        if newest_line or not is_file_end
        else all_older_lines
    )


def _lines_within_cap(
    all_lines: list[bytes], may_pass_cap: bool, caps: ScanCaps
) -> tuple[list[bytes], bool]:
    if not may_pass_cap:
        return all_lines, True
    for each_index, each_line in enumerate(all_lines):
        if len(each_line) > caps.line_byte_cap:
            return all_lines[:each_index], False
    return all_lines, True


def _byte_lines_newest_first(
    transcript: BinaryIO,
    block_size: int,
    keeps_reading: Callable[[], bool],
    caps: ScanCaps,
) -> Iterator[bytes]:
    all_newer_parts: list[bytes] = []
    newer_byte_count = 0
    is_file_end = True
    oldest_start = 0
    for each_start, each_block in _blocks_newest_first(
        transcript, block_size, keeps_reading
    ):
        oldest_start = each_start
        all_pieces = _block_pieces(each_block)
        is_within_cap = True
        if len(all_pieces) > 1:
            all_lines = _complete_lines(all_pieces, all_newer_parts, is_file_end)
            may_pass_cap = len(each_block) + newer_byte_count > caps.line_byte_cap
            all_lines, is_within_cap = _lines_within_cap(all_lines, may_pass_cap, caps)
            yield from all_lines
            is_file_end, all_newer_parts, newer_byte_count = False, [], 0
        all_newer_parts.append(all_pieces[0])
        newer_byte_count += len(all_pieces[0])
        if not is_within_cap or newer_byte_count > caps.line_byte_cap:
            caps.on_cap_passed()
            return
    oldest_line = b"".join(reversed(all_newer_parts))
    if oldest_start == 0 and (oldest_line or not is_file_end):
        yield oldest_line


def _open_line_byte_count(block: bytes, earlier_open_byte_count: int) -> int:
    last_break = max(block.rfind(NEWLINE_BYTE), block.rfind(CARRIAGE_RETURN_BYTE))
    return (
        earlier_open_byte_count + len(block)
        if last_break < 0
        else len(block) - last_break - 1
    )


def _forward_copy(
    transcript: BinaryIO,
    block_size: int,
    keeps_reading: Callable[[], bool],
    caps: ScanCaps,
) -> BinaryIO:
    copy = io.BytesIO()
    open_line_byte_count = 0
    while keeps_reading():
        block = transcript.read(block_size)
        if not block:
            return copy
        open_line_byte_count = _open_line_byte_count(block, open_line_byte_count)
        is_over_copy_cap = copy.tell() + len(block) > caps.forward_copy_byte_cap
        if is_over_copy_cap or open_line_byte_count > caps.line_byte_cap:
            caps.on_cap_passed()
            break
        copy.write(block)
    return io.BytesIO()


def _seeks_to_end(transcript: BinaryIO) -> bool:
    if not transcript.seekable():
        return False
    try:
        transcript.seek(0, SEEK_END)
    except OSError:
        return False
    return True


def _seekable_byte_lines(
    transcript: BinaryIO,
    block_size: int,
    keeps_reading: Callable[[], bool],
    caps: ScanCaps,
) -> Iterator[bytes]:
    if not _seeks_to_end(transcript):
        transcript = _forward_copy(transcript, block_size, keeps_reading, caps)
    yield from _byte_lines_newest_first(transcript, block_size, keeps_reading, caps)


def transcript_lines_newest_first(
    transcript: BinaryIO,
    encoding: str,
    errors: str,
    block_size: int = TRANSCRIPT_BLOCK_BYTES,
    keeps_reading: Callable[[], bool] = _always_reads,
    caps: ScanCaps | None = None,
) -> Iterator[str]:
    """Yield each line of a binary transcript, newest first, split where text mode splits it.

    ::

        b"one\\ntwo\\r\\nthree\\rfour"   -> "four", "three", "two", "one"

    ``\\n``, ``\\r\\n`` and a lone ``\\r`` end lines. A no from ``keeps_reading``, or a passed
    cap, stops the reader. A transcript that cannot seek to its end is copied forward first.

    Args:
        transcript: The transcript opened in binary mode.
        encoding: The text encoding of the transcript.
        errors: The decode errors policy, such as ``"replace"``.
        block_size: The bytes read from the file at a time.
        keeps_reading: Whether the reader may read one more block.
        caps: The byte caps, or None for the default ``ScanCaps()``.
    """
    scan_caps = ScanCaps() if caps is None else caps
    all_byte_lines = _seekable_byte_lines(
        transcript, block_size, keeps_reading, scan_caps
    )
    return (each_line.decode(encoding, errors) for each_line in all_byte_lines)


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


def _succeeded_result_ids(all_entry_fields: dict[str, object]) -> set[object]:
    return {
        each_block.get(TOOL_USE_ID_FIELD)
        for each_block in _content_blocks(all_entry_fields, USER_ENTRY_TYPE)
        if each_block.get("type") == TOOL_RESULT_BLOCK_TYPE and each_block.get(IS_ERROR_FIELD) is not True
    }


def _task_notification_text(all_entry_fields: dict[str, object]) -> str | None:
    origin = all_entry_fields.get(ORIGIN_FIELD)
    if not isinstance(origin, dict) or origin.get(ORIGIN_KIND_FIELD) != TASK_NOTIFICATION_ORIGIN_KIND:
        return None
    return _user_command_text(all_entry_fields) or ""


def _background_ids_finished_without_error(notification_text: str) -> set[object]:
    if re.search(TASK_NOTIFICATION_SUCCESS_PATTERN, notification_text) is None:
        return set()
    return set(re.findall(TASK_NOTIFICATION_TOOL_USE_ID_PATTERN, notification_text))


def tool_calls_since_last_prompt(all_transcript_lines: Iterable[str]) -> list[TranscriptToolCall]:
    """Return the tool calls after the last user prompt, in order, each marked by whether it succeeded.

    ::

        prompt, reply call, its result without an error  -> [reply succeeded]
        prompt, reply call, its result with is_error     -> [reply failed]
        prompt, resolve call with no result yet          -> [resolve failed]
        reply call and result, then a new prompt         -> []
        background call, started                          -> [call failed]
        background call, notice of exit code 0            -> [call succeeded]
        background call, notice of exit code 3            -> [call failed]

    A hook that denies a call leaves an errored result, so a denied call does
    not count as a success. A tool result leaves the turn open. A background
    task notice is no user prompt, so it leaves the turn open too. A call with
    ``run_in_background`` set succeeds only when the notice that names its
    tool use id reports a completed status with exit code 0.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
    """
    all_calls: list[tuple[object, str, dict[str, object]]] = []
    all_succeeded_ids: set[object] = set()
    all_finished_background_ids: set[object] = set()
    all_entries = (each_entry for each_entry in map(_parsed_entry, all_transcript_lines) if each_entry is not None)
    for each_entry_fields in all_entries:
        notification_text = _task_notification_text(each_entry_fields)
        if notification_text is not None:
            all_finished_background_ids.update(_background_ids_finished_without_error(notification_text))
            continue
        if _is_user_prompt(each_entry_fields):
            all_calls, all_succeeded_ids, all_finished_background_ids = [], set(), set()
            continue
        all_calls.extend(_tool_use_calls(each_entry_fields))
        all_succeeded_ids.update(_succeeded_result_ids(each_entry_fields))
    return [
        TranscriptToolCall(
            each_name,
            each_input,
            each_id is not None
            and each_id in all_succeeded_ids
            and (each_input.get(RUN_IN_BACKGROUND_INPUT_KEY) is not True or each_id in all_finished_background_ids),
        )
        for each_id, each_name, each_input in all_calls
    ]
