#!/usr/bin/env python3
"""PreToolUse hook: refuse to publish an artifact page nobody has looked at.

An agent that writes a page and publishes it without rendering it cannot know
the page matches the ask. The hook walks the session transcript and allows the
publish only when a Read opened an image file whose modification time is at
least the page file's::

    Write page.html -> shoot shot.png -> Read shot.png -> publish -> allowed
    Write page.html -> publish                                    -> refused
    Read shot.png -> change page.html in any tool -> publish      -> refused
    Read an image older than the page -> publish                  -> refused

A Read that returned an error does not count. A non-HTML file, an asset
upload, a non-publish action and an unreadable transcript all pass, so the
hook never fails closed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.artifact_look_gate_constants import (
    ALL_IMAGE_FILE_SUFFIXES,
    ALL_PAGE_FILE_SUFFIXES,
    ARTIFACT_ACTION_INPUT_KEY,
    ARTIFACT_ASSET_INPUT_KEY,
    ARTIFACT_PUBLISH_ACTION,
    ARTIFACT_TOOL_NAME,
    ASSISTANT_ENTRY_TYPE,
    DENY_DECISION,
    FILE_PATH_INPUT_KEY,
    IMAGE_READING_TOOL_NAME,
    PRE_TOOL_USE_EVENT_NAME,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    TRANSCRIPT_PATH_KEY,
    UNSEEN_PAGE_REASON_TEMPLATE,
    USER_ENTRY_TYPE,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def _content_blocks(
    all_entry_fields: dict[str, object], entry_type: str
) -> list[dict[str, object]]:
    if all_entry_fields.get("type") != entry_type:
        return []
    message = all_entry_fields.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [each_block for each_block in content if isinstance(each_block, dict)]


def _parsed_entry(transcript_line: str) -> dict[str, object]:
    try:
        parsed_line = json.loads(transcript_line)
    except json.JSONDecodeError:
        return {}
    return parsed_line if isinstance(parsed_line, dict) else {}


def _failed_tool_use_ids(all_entries: list[dict[str, object]]) -> set[str]:
    return {
        str(each_block.get("tool_use_id"))
        for each_entry in all_entries
        for each_block in _content_blocks(each_entry, USER_ENTRY_TYPE)
        if each_block.get("type") == TOOL_RESULT_BLOCK_TYPE and each_block.get("is_error")
    }


def _tool_calls(all_entries: list[dict[str, object]]) -> list[tuple[str, object, object]]:
    return [
        (str(each_block.get("id")), each_block.get("name"), tool_input.get(FILE_PATH_INPUT_KEY))
        for each_entry in all_entries
        for each_block in _content_blocks(each_entry, ASSISTANT_ENTRY_TYPE)
        if each_block.get("type") == TOOL_USE_BLOCK_TYPE
        and isinstance(tool_input := each_block.get("input"), dict)
    ]


def _is_image_read(tool_name: object, file_path: object) -> bool:
    return (
        tool_name == IMAGE_READING_TOOL_NAME
        and isinstance(file_path, str)
        and file_path.lower().endswith(ALL_IMAGE_FILE_SUFFIXES)
    )


def _modified_time(file_path: str) -> float | None:
    try:
        return Path(file_path).stat().st_mtime
    except OSError:
        return None


def page_was_looked_at(all_transcript_lines: list[str], page_path: str) -> bool:
    """Return True when a screenshot made after the page's last change was read.

    The page's modification time covers every way it can change, including a
    Bash command or a subagent. A Read counts only when it succeeded and its
    image file is at least as new as the page.

    Args:
        all_transcript_lines: The session transcript, one JSON record per line.
        page_path: The file the Artifact call publishes.
    """
    page_modified_time = _modified_time(page_path)
    if page_modified_time is None:
        return False
    all_entries = [_parsed_entry(each_line) for each_line in all_transcript_lines]
    all_failed_ids = _failed_tool_use_ids(all_entries)
    for each_id, each_tool_name, each_file_path in _tool_calls(all_entries):
        if not _is_image_read(each_tool_name, each_file_path) or each_id in all_failed_ids:
            continue
        image_modified_time = _modified_time(str(each_file_path))
        if image_modified_time is not None and image_modified_time >= page_modified_time:
            return True
    return False


def _published_page_path(all_hook_fields: dict[str, object]) -> str | None:
    tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    if all_hook_fields.get(TOOL_NAME_KEY) != ARTIFACT_TOOL_NAME or not isinstance(tool_input, dict):
        return None
    page_path = tool_input.get(FILE_PATH_INPUT_KEY)
    is_page_publish = (
        tool_input.get(ARTIFACT_ACTION_INPUT_KEY, ARTIFACT_PUBLISH_ACTION) == ARTIFACT_PUBLISH_ACTION
        and tool_input.get(ARTIFACT_ASSET_INPUT_KEY) is not True
        and isinstance(page_path, str)
        and page_path.lower().endswith(ALL_PAGE_FILE_SUFFIXES)
    )
    return page_path if is_page_publish else None


def unseen_page_reason(all_hook_fields: dict[str, object]) -> str | None:
    """Return the refusal for an unseen page publish, or None to allow it.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    page_path = _published_page_path(all_hook_fields)
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_KEY)
    if page_path is None or not isinstance(transcript_path, str):
        return None
    try:
        all_transcript_lines = Path(transcript_path).read_text(
            encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
        ).splitlines()
    except OSError:
        return None
    if page_was_looked_at(all_transcript_lines, page_path):
        return None
    return UNSEEN_PAGE_REASON_TEMPLATE.format(page_path=page_path)


def main() -> int:
    """Read the PreToolUse payload and print a deny decision for an unseen page.

    Returns:
        0 in every case; the decision travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return 0
    refusal_reason = unseen_page_reason(hook_payload)
    if refusal_reason is not None:
        sys.stdout.write(
            json.dumps(
                {
                    HOOK_SPECIFIC_OUTPUT_KEY: {
                        HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
                        PERMISSION_DECISION_KEY: DENY_DECISION,
                        PERMISSION_DECISION_REASON_KEY: refusal_reason,
                    }
                }
            )
        )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
