#!/usr/bin/env python3
"""PreToolUse hook: refuse to publish an artifact page nobody has looked at.

An agent that writes a page and publishes it without rendering it cannot know
the page matches the ask. The hook walks the session transcript and allows the
publish only when an image was opened with Read after the page file was last
written::

    Write page.html -> Read shot.png -> Artifact publish page.html  -> allowed
    Write page.html -> Artifact publish page.html                   -> refused
    Read shot.png -> Edit page.html -> Artifact publish page.html   -> refused

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
    ALL_PAGE_WRITING_TOOL_NAMES,
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


def _same_path(first_path: object, second_path: str) -> bool:
    return isinstance(first_path, str) and Path(first_path).resolve() == Path(second_path).resolve()


def page_was_looked_at(all_transcript_lines: list[str], page_path: str) -> bool:
    """Return True when an image was read after the page file was last written.

    Args:
        all_transcript_lines: The session transcript, one JSON record per line.
        page_path: The file the Artifact call publishes.
    """
    all_image_read_ids: list[str] = []
    all_failed_tool_use_ids: set[str] = set()
    for each_line in all_transcript_lines:
        try:
            all_entry_fields = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(all_entry_fields, dict):
            continue
        for each_block in _content_blocks(all_entry_fields, USER_ENTRY_TYPE):
            if each_block.get("type") == TOOL_RESULT_BLOCK_TYPE and each_block.get("is_error"):
                all_failed_tool_use_ids.add(str(each_block.get("tool_use_id")))
        for each_block in _content_blocks(all_entry_fields, ASSISTANT_ENTRY_TYPE):
            if each_block.get("type") != TOOL_USE_BLOCK_TYPE:
                continue
            tool_input = each_block.get("input")
            if not isinstance(tool_input, dict):
                continue
            written_or_read_path = tool_input.get(FILE_PATH_INPUT_KEY)
            tool_name = each_block.get("name")
            if tool_name in ALL_PAGE_WRITING_TOOL_NAMES and _same_path(
                written_or_read_path, page_path
            ):
                all_image_read_ids = []
            elif (
                tool_name == IMAGE_READING_TOOL_NAME
                and isinstance(written_or_read_path, str)
                and written_or_read_path.lower().endswith(ALL_IMAGE_FILE_SUFFIXES)
            ):
                all_image_read_ids.append(str(each_block.get("id")))
    return any(each_read_id not in all_failed_tool_use_ids for each_read_id in all_image_read_ids)


def unseen_page_reason(all_hook_fields: dict[str, object]) -> str | None:
    """Return the refusal for an unseen page publish, or None to allow it.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    if all_hook_fields.get(TOOL_NAME_KEY) != ARTIFACT_TOOL_NAME:
        return None
    tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return None
    page_path = tool_input.get(FILE_PATH_INPUT_KEY)
    if (
        tool_input.get(ARTIFACT_ACTION_INPUT_KEY, ARTIFACT_PUBLISH_ACTION)
        != ARTIFACT_PUBLISH_ACTION
        or tool_input.get(ARTIFACT_ASSET_INPUT_KEY) is True
        or not isinstance(page_path, str)
        or not page_path.lower().endswith(ALL_PAGE_FILE_SUFFIXES)
    ):
        return None
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(transcript_path, str):
        return None
    try:
        all_transcript_lines = (
            Path(transcript_path)
            .read_text(encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS)
            .splitlines()
        )
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
