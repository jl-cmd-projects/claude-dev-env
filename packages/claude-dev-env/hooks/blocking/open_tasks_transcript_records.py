"""Read a transcript file into records, and read what one record holds.

One record can hold the prompt text that starts a turn, a tool call that is work,
a read, or a question card, the files a ``SendUserFile`` call sends, or the
names of the tools a Claude Code session lists.
``open_tasks_transcript`` folds these readers over every record. Its module
docstring lists which records start a turn and which tool calls count as work.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hooks_constants.send_user_file_worktree_root_gate_constants import SEND_USER_FILE_TOOL_NAME
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_DEFERRED_TOOLS_DELTA_NAME_KEYS,
    ALL_SKIPPED_PROMPT_FLAGS,
    ALL_CODEX_TOOL_CALL_TYPES,
    ATTACHMENT_KEY,
    DEFERRED_TOOLS_DELTA_ATTACHMENT_TYPE,
    DEFERRED_TOOLS_RECORD_ATTACHMENT_TYPE,
    DEFERRED_TOOLS_RECORD_ENTRIES_KEY,
    PROMPT_SNAPSHOT_ATTACHMENT_TYPE,
    PROMPT_SNAPSHOT_TOOLS_KEY,
    ALL_NON_WORK_TOOL_NAMES,
    ALL_QUESTION_TOOL_NAMES,
    ALL_READ_TOOL_NAMES,
    ALL_READ_WORDS,
    ALL_WRITE_WORDS,
    ASSISTANT_ROLE,
    CODEX_LOCAL_SHELL_CALL_TYPE,
    CODEX_MESSAGE_TYPE,
    CODEX_PAYLOAD_KEY,
    CODEX_PLAN_TOOL_NAME,
    CODEX_RESPONSE_ITEM_TYPE,
    CONTENT_KEY,
    MESSAGE_KEY,
    RECORD_TYPE_KEY,
    ROLE_KEY,
    SENT_FILES_KEY,
    STOP_HOOK_FEEDBACK_PREFIX,
    SESSION_TITLE_TOOL_SUFFIX,
    TEXT_KEY,
    RECORD_SEPARATOR,
    TOOL_NAME_SERVER_SEPARATOR,
    TOOL_NAME_WORD_BREAK_PATTERN,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    USER_RECORD_TYPE,
    USER_ROLE,
    UTF8_ENCODING,
    WORD_SEPARATOR,
)


def normalized_text(text: str) -> str:
    """Return the text lowercased with each run of whitespace collapsed to one space."""
    return WORD_SEPARATOR.join(text.lower().split())


def parsed_object(json_text: str) -> dict[str, object] | None:
    """Return the JSON object in the text, or None for anything else.

    Text that is no JSON, or JSON nested too deep to parse, is None.
    """
    try:
        parsed_value = json.loads(json_text)
    except (ValueError, RecursionError):
        return None
    return parsed_value if isinstance(parsed_value, dict) else None


def _transcript_records(transcript_path: object) -> list[dict[str, object]]:
    if not isinstance(transcript_path, str):
        return []
    try:
        transcript_text = Path(transcript_path).read_text(encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
    except (OSError, ValueError):
        return []
    all_records = (parsed_object(each_line) for each_line in transcript_text.split(RECORD_SEPARATOR))
    return [each_record for each_record in all_records if each_record is not None]


def _content_blocks(all_record_fields: dict[str, object]) -> list[dict[str, object]]:
    message_body = all_record_fields.get(MESSAGE_KEY)
    content_value = message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
    if not isinstance(content_value, list):
        return []
    return [each_block for each_block in content_value if isinstance(each_block, dict)]


def _text_of_blocks(all_blocks: list[dict[str, object]]) -> str:
    return WORD_SEPARATOR.join(
        str(each_block.get(TEXT_KEY, "")) for each_block in all_blocks if isinstance(each_block.get(TEXT_KEY), str)
    )


def claude_prompt_text(all_record_fields: dict[str, object]) -> str | None:
    """Return the prompt text of a record that starts a turn, or None for any other record."""
    message_body = all_record_fields.get(MESSAGE_KEY)
    message_role = message_body.get(ROLE_KEY) if isinstance(message_body, dict) else None
    if USER_RECORD_TYPE != all_record_fields.get(RECORD_TYPE_KEY) and USER_ROLE not in (all_record_fields.get(ROLE_KEY), message_role):
        return None
    if any(all_record_fields.get(each_flag) for each_flag in ALL_SKIPPED_PROMPT_FLAGS):
        return None
    content_value = message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
    if isinstance(content_value, str):
        prompt_text = content_value
    else:
        all_blocks = _content_blocks(all_record_fields)
        if any(each_block.get(RECORD_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE for each_block in all_blocks):
            return None
        if any(each_block.get(RECORD_TYPE_KEY) != TEXT_KEY for each_block in all_blocks):
            return _text_of_blocks(all_blocks)
        prompt_text = _text_of_blocks(all_blocks)
    if not prompt_text.strip() or prompt_text.lstrip().startswith(STOP_HOOK_FEEDBACK_PREFIX):
        return None
    return prompt_text


def _codex_payload(all_record_fields: dict[str, object]) -> dict[str, object] | None:
    payload_body = all_record_fields.get(CODEX_PAYLOAD_KEY)
    if all_record_fields.get(RECORD_TYPE_KEY) != CODEX_RESPONSE_ITEM_TYPE or not isinstance(payload_body, dict):
        return None
    return payload_body


def codex_prompt_text(all_record_fields: dict[str, object]) -> str | None:
    """Return the text of a Codex user message record, or None for any other record."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) != CODEX_MESSAGE_TYPE or payload_body.get(ROLE_KEY) != USER_ROLE:
        return None
    content_value = payload_body.get(CONTENT_KEY)
    if isinstance(content_value, str):
        return content_value
    all_blocks = [each_block for each_block in content_value if isinstance(each_block, dict)] if isinstance(content_value, list) else []
    return _text_of_blocks(all_blocks)


def is_codex_work_call(all_record_fields: dict[str, object]) -> bool:
    """Return True for a Codex tool call record other than ``update_plan`` or a question card call."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) not in ALL_CODEX_TOOL_CALL_TYPES:
        return False
    tool_name = payload_body.get(TOOL_NAME_KEY)
    return tool_name != CODEX_PLAN_TOOL_NAME and is_work_tool_name(tool_name)


def is_codex_read_call(all_record_fields: dict[str, object]) -> bool:
    """Return True for a Codex tool call record whose tool can read state; a ``local_shell_call`` carries no name and counts."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) not in ALL_CODEX_TOOL_CALL_TYPES:
        return False
    if payload_body.get(RECORD_TYPE_KEY) == CODEX_LOCAL_SHELL_CALL_TYPE:
        return True
    return is_read_tool_name(payload_body.get(TOOL_NAME_KEY))


def is_codex_question_call(all_record_fields: dict[str, object]) -> bool:
    """Return True for a Codex tool call record that sends a question card."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) not in ALL_CODEX_TOOL_CALL_TYPES:
        return False
    return payload_body.get(TOOL_NAME_KEY) in ALL_QUESTION_TOOL_NAMES


def is_work_tool_name(tool_name: object) -> bool:
    """Return True for a tool name other than a non-work tool or the session title tool."""
    return not (
        isinstance(tool_name, str)
        and (tool_name in ALL_NON_WORK_TOOL_NAMES or tool_name.endswith(SESSION_TITLE_TOOL_SUFFIX))
    )


def is_read_tool_name(tool_name: object) -> bool:
    """Return True for a tool that can read state.

    ::

        Bash, Read, WebFetch, Agent, shell         -> True
        mcp__github__pull_request_read             -> True
        mcp__claude-code-remote__get_session       -> True
        ReadMcpResourceTool, mcp__x__getIssue      -> True
        Write, SendUserFile, TaskUpdate            -> False
        TaskList, TaskGet                          -> False
        mcp__tracker__update_status, AppendLog     -> False
        mcp__logs__write_entry                     -> False

    A name counts when one of its words is a read word and none is a write
    word. Only the part after the last double underscore is read, so a server
    name never decides it. Words are split at underscores, hyphens, and a
    capital that follows a lower-case letter or a digit. A tool that is no work tool never counts: TaskList and TaskGet read
    the task list itself, and ToolSearch and the question tools read no state.
    """
    if not isinstance(tool_name, str) or tool_name in ALL_NON_WORK_TOOL_NAMES:
        return False
    if tool_name in ALL_READ_TOOL_NAMES:
        return True
    action_name = tool_name.rsplit(TOOL_NAME_SERVER_SEPARATOR, 1)[-1]
    all_name_words = {each_word.lower() for each_word in re.split(TOOL_NAME_WORD_BREAK_PATTERN, action_name)}
    return not ALL_READ_WORDS.isdisjoint(all_name_words) and ALL_WRITE_WORDS.isdisjoint(all_name_words)


def send_call_file_paths(tool_name: str, all_input_fields: dict[str, object]) -> list[str]:
    """Return the file paths a SendUserFile call sends, or an empty list for any other call."""
    all_sent_files = all_input_fields.get(SENT_FILES_KEY)
    if tool_name != SEND_USER_FILE_TOOL_NAME or not isinstance(all_sent_files, list):
        return []
    return [each_path for each_path in all_sent_files if isinstance(each_path, str)]


def _entry_names(all_entries: object) -> list[str]:
    if not isinstance(all_entries, list):
        return []
    return [
        each_entry[TOOL_NAME_KEY]
        for each_entry in all_entries
        if isinstance(each_entry, dict) and isinstance(each_entry.get(TOOL_NAME_KEY), str)
    ]


def listed_tool_names(all_record_fields: dict[str, object]) -> tuple[str, list[str]] | None:
    """Return the attachment type and tool names of a Claude Code record that lists the session's tools.

    ::

        prompt_snapshot with a tools list       -> ("prompt_snapshot", the inline tool names)
        deferred_tools_delta                    -> ("deferred_tools_delta", the added, readded,
                                                    surfaced, and loaded names)
        deferred_tools_record                   -> ("deferred_tools_record", the names ToolSearch loaded)
        prompt_snapshot with no tools list      -> None
        any other record                        -> None

    Names come only from these fields, so a tool name inside prose never counts.
    """
    attachment_body = all_record_fields.get(ATTACHMENT_KEY)
    if not isinstance(attachment_body, dict):
        return None
    attachment_type = attachment_body.get(RECORD_TYPE_KEY)
    if attachment_type == PROMPT_SNAPSHOT_ATTACHMENT_TYPE:
        all_inline_tools = attachment_body.get(PROMPT_SNAPSHOT_TOOLS_KEY)
        if not isinstance(all_inline_tools, list):
            return None
        return attachment_type, _entry_names(all_inline_tools)
    if attachment_type == DEFERRED_TOOLS_RECORD_ATTACHMENT_TYPE:
        return attachment_type, _entry_names(attachment_body.get(DEFERRED_TOOLS_RECORD_ENTRIES_KEY))
    if attachment_type == DEFERRED_TOOLS_DELTA_ATTACHMENT_TYPE:
        all_delta_names = [
            each_name
            for each_key in ALL_DEFERRED_TOOLS_DELTA_NAME_KEYS
            for each_delta_value in [attachment_body.get(each_key)]
            if isinstance(each_delta_value, list)
            for each_name in each_delta_value
            if isinstance(each_name, str)
        ]
        return attachment_type, all_delta_names
    return None


def is_assistant_record(all_record_fields: dict[str, object]) -> bool:
    """Return True for a record the assistant wrote, by its type, its role, or its message role."""
    message_body = all_record_fields.get(MESSAGE_KEY)
    message_role = message_body.get(ROLE_KEY) if isinstance(message_body, dict) else None
    return ASSISTANT_ROLE in (all_record_fields.get(ROLE_KEY), all_record_fields.get(RECORD_TYPE_KEY), message_role)
