#!/usr/bin/env python3
"""PreToolUse hook that denies a write growing an agent context file past its budget.

The edited file's own repository supplies ``.claude/context-budget.json``; a
repository without one uses the built-in kinds and treats the file's current
content as its baseline entry. The hook denies only what an edit adds: an edit
that only shrinks a file passes, and the CI ratchet never runs here.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from blocking.codex_apply_patch import (
    CodexPatchError,
    parse_codex_apply_patch,
    payload_patch_command,
)
from context_budget.findings import edit_findings
from context_budget.model import BudgetPolicy, ContextBudgetPolicyError
from context_budget.policy_file import default_policy, find_repository_root, read_policy_file
from hooks_constants.context_budget_constants import (
    CONTENT_KEY,
    CONTEXT_BUDGET_BLOCK_PREFIX,
    CONTEXT_BUDGET_HOOK_NAME,
    CONTEXT_BUDGET_NOTICE,
    CONTEXT_BUDGET_REASON_SEPARATOR,
    CWD_KEY,
    FILE_PATH_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    UTF8_ENCODING,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.multi_edit_reconstruction import apply_edits, edits_for_tool
from hooks_constants.pre_tool_use_dispatcher_constants import (
    ALL_WRITE_EDIT_MULTI_EDIT_TOOL_NAMES,
    APPLY_PATCH_TOOL_NAME,
    HOOK_EVENT_NAME,
    WRITE_TOOL_NAME,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin

EditedText = tuple[Path, str | None, str]


def _read_optional_text(file_path: Path) -> str | None:
    try:
        return file_path.read_text(encoding=UTF8_ENCODING)
    except (OSError, UnicodeDecodeError):
        return None


def _absolute_path(raw_path: str, payload_by_key: Mapping[str, object]) -> Path:
    candidate = Path(raw_path).expanduser()
    working_directory = payload_by_key.get(CWD_KEY)
    if not candidate.is_absolute() and isinstance(working_directory, str):
        candidate = Path(working_directory) / candidate
    return candidate.resolve()


def _edited_texts(payload_by_key: Mapping[str, object]) -> Iterator[EditedText]:
    tool_name = payload_by_key.get(TOOL_NAME_KEY)
    tool_input = payload_by_key.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return
    if tool_name == APPLY_PATCH_TOOL_NAME:
        command, working_directory = payload_patch_command(dict(payload_by_key), tool_input)
        try:
            all_patch_files = parse_codex_apply_patch(command, working_directory)
        except CodexPatchError:
            return
        for each_file in all_patch_files:
            yield Path(each_file.file_path), each_file.prior_content or None, each_file.post_content
        return
    raw_path = tool_input.get(FILE_PATH_KEY)
    if tool_name not in ALL_WRITE_EDIT_MULTI_EDIT_TOOL_NAMES or not isinstance(raw_path, str):
        return
    file_path = _absolute_path(raw_path, payload_by_key)
    prior_text = _read_optional_text(file_path)
    if tool_name == WRITE_TOOL_NAME:
        content = tool_input.get(CONTENT_KEY)
        if isinstance(content, str):
            yield file_path, prior_text, content
    elif prior_text is not None:
        yield file_path, prior_text, apply_edits(prior_text, edits_for_tool(str(tool_name), tool_input))


def _policy_for(repository_root: Path) -> tuple[BudgetPolicy, bool]:
    try:
        policy = read_policy_file(repository_root)
    except ContextBudgetPolicyError:
        policy = None
    if policy is None:
        return default_policy(), True
    return policy, False


def _messages_for(edited_text: EditedText) -> list[str]:
    file_path, prior_text, post_text = edited_text
    repository_root = find_repository_root(file_path)
    if repository_root is None:
        return []
    policy, is_prior_the_baseline = _policy_for(repository_root)
    relative_path = file_path.relative_to(repository_root).as_posix()
    all_findings = edit_findings(policy, relative_path, prior_text, post_text, is_prior_the_baseline)
    return [each.message for each in all_findings]


def evaluate(payload_by_key: Mapping[str, object]) -> str | None:
    """Return a deny reason when a write adds context past its budget.

    Args:
        payload_by_key: The PreToolUse payload.

    Returns:
        The deny reason, or None to allow.
    """
    all_messages = [
        each_message
        for each_edited_text in _edited_texts(payload_by_key)
        for each_message in _messages_for(each_edited_text)
    ]
    if not all_messages:
        return None
    return CONTEXT_BUDGET_BLOCK_PREFIX + CONTEXT_BUDGET_REASON_SEPARATOR.join(all_messages)


def build_deny_payload(deny_reason: str, tool_name: str | None) -> dict[str, object]:
    """Build the PreToolUse deny response and log the block.

    Args:
        deny_reason: The reason ``evaluate`` returned.
        tool_name: The intercepted tool name.

    Returns:
        The deny payload.
    """
    log_hook_block(
        calling_hook_name=CONTEXT_BUDGET_HOOK_NAME,
        hook_event=HOOK_EVENT_NAME,
        block_reason=deny_reason,
        tool_name=tool_name,
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": "deny",
            "permissionDecisionReason": deny_reason,
        },
        "systemMessage": CONTEXT_BUDGET_NOTICE,
    }


def main() -> None:
    """Read one hook payload and emit a deny response when needed."""
    payload_by_key = read_hook_input_dictionary_from_stdin()
    if payload_by_key is None:
        return
    deny_reason = evaluate(payload_by_key)
    if deny_reason is None:
        return
    raw_tool_name = payload_by_key.get(TOOL_NAME_KEY)
    tool_name = raw_tool_name if isinstance(raw_tool_name, str) else None
    sys.stdout.write(json.dumps(build_deny_payload(deny_reason, tool_name)) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
