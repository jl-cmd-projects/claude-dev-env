"""Deny an edit to the pull request proof gate while its last deny in the session has no passing create call after it."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.codex_apply_patch import payload_patch_target_paths
from blocking.pr_lifecycle_skill_gate import transcript_paths
from blocking.pull_request_proof import is_create_call
from blocking.step_note_gate import entry_content_blocks
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    DENY_DECISION,
    HOOK_EVENT_NAME,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_dispatcher_constants import APPLY_PATCH_TOOL_NAME
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.pull_request_proof_constants import (
    ALL_PROOF_GATE_DENY_MARKERS,
    ALL_PROOF_GATE_FILE_NAMES,
    GATE_EDIT_BEFORE_ROUTE_REASON,
    LINE_SEPARATOR,
    POSIX_PATH_SEPARATOR,
    WINDOWS_PATH_SEPARATOR,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from hooks_constants.spawn_readiness_hook_constants import (
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
)


def _content_blocks(transcript_line: str) -> list[dict]:
    try:
        entry = json.loads(transcript_line)
    except json.JSONDecodeError:
        return []
    if not isinstance(entry, dict) or not isinstance(entry.get("message"), dict):
        return []
    return entry_content_blocks(entry)


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return LINE_SEPARATOR.join(
        each_block["text"]
        for each_block in content
        if isinstance(each_block, dict) and isinstance(each_block.get("text"), str)
    )


def _is_proof_gate_deny(all_block_fields: dict[str, object]) -> bool:
    result_text = _result_text(all_block_fields.get("content"))
    return any(each_marker in result_text for each_marker in ALL_PROOF_GATE_DENY_MARKERS)


def _deny_state_after(
    all_block_fields: dict[str, object], all_create_tool_use_ids: set[str], is_deny_open: bool
) -> bool:
    if all_block_fields.get("type") == TOOL_USE_BLOCK_TYPE:
        tool_use_id = all_block_fields.get("id")
        payload = {"tool_name": all_block_fields.get("name"), "tool_input": all_block_fields.get("input")}
        if isinstance(tool_use_id, str) and is_create_call(payload):
            all_create_tool_use_ids.add(tool_use_id)
        return is_deny_open
    if all_block_fields.get("type") != TOOL_RESULT_BLOCK_TYPE:
        return is_deny_open
    result_tool_use_id = all_block_fields.get("tool_use_id")
    if not isinstance(result_tool_use_id, str) or result_tool_use_id not in all_create_tool_use_ids:
        return is_deny_open
    if all_block_fields.get("is_error") is True:
        return is_deny_open or _is_proof_gate_deny(all_block_fields)
    return False


def has_open_deny(all_transcript_lines: Iterable[str]) -> bool:
    """Return whether the proof gate's last deny in a transcript has no passing create call after it.

    ::

        create denied with the proof gate's reason             -> True
        create denied, later create returned without an error  -> False
        no deny from the proof gate                            -> False

    A deny is an errored result of a create call that carries one of the proof gate's guide paths.

    Args:
        all_transcript_lines: The JSON lines of a session transcript, oldest first.
    """
    all_create_tool_use_ids: set[str] = set()
    is_deny_open = False
    for each_line in all_transcript_lines:
        for each_block in _content_blocks(each_line):
            is_deny_open = _deny_state_after(each_block, all_create_tool_use_ids, is_deny_open)
    return is_deny_open


def _transcript_has_open_deny(transcript_path: str) -> bool:
    try:
        with open(transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            return has_open_deny(transcript)
    except OSError:
        return False


def _target_paths(all_payload_fields: Mapping[str, object]) -> tuple[str, ...]:
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_input, dict):
        return ()
    if all_payload_fields.get("tool_name") == APPLY_PATCH_TOOL_NAME:
        try:
            return payload_patch_target_paths(dict(all_payload_fields), tool_input)
        except ValueError:
            return ()
    file_path = tool_input.get("file_path")
    return (file_path,) if isinstance(file_path, str) else ()


def _edits_proof_gate(all_payload_fields: Mapping[str, object]) -> bool:
    return any(
        Path(each_path.replace(WINDOWS_PATH_SEPARATOR, POSIX_PATH_SEPARATOR)).name.lower()
        in ALL_PROOF_GATE_FILE_NAMES
        for each_path in _target_paths(all_payload_fields)
    )


def gate_edit_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason for an edit to the proof gate while its last deny is still open, else None.

    ::

        Edit or apply_patch of a gate file after an open deny       -> GATE_EDIT_BEFORE_ROUTE_REASON
        Edit of pull_request_proof.py after a later passing create  -> None
        Edit of any other file, or no readable transcript           -> None

    Args:
        all_payload_fields: The parsed PreToolUse input of a Write, Edit, MultiEdit or apply_patch call.
    """
    if not _edits_proof_gate(all_payload_fields):
        return None
    if any(_transcript_has_open_deny(each_path) for each_path in transcript_paths(dict(all_payload_fields))):
        return GATE_EDIT_BEFORE_ROUTE_REASON
    return None


def _gate_edit_decision(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    reason = gate_edit_reason(all_payload_fields)
    if reason is None:
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: reason,
        }
    }


def main() -> int:
    """Read one Write, Edit, MultiEdit or apply_patch payload and print a deny when it edits the proof gate too soon."""
    return print_decision_from_stdin(_gate_edit_decision)


if __name__ == "__main__":
    sys.exit(main())
