#!/usr/bin/env python3
"""PreToolUse hook that caps the prose of a GitHub comment before it posts.

A comment, review, or review reply posted through the GitHub tools or the
``gh pr|issue comment|review`` commands gets the reply length check: at most
MAXIMUM_SENTENCE_COUNT sentences of at most MAXIMUM_WORDS_PER_SENTENCE words.
Fenced code blocks and collapsed ``<details>`` blocks carry no words.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from reply_length_gate import length_violation
from gh_post_body_texts import extract_gh_post_body_texts_for_privacy_gate, extract_mcp_body_texts
from hooks_constants.github_comment_length_gate_constants import (
    ALL_CHECKED_MCP_TOOL_NAMES,
    BASH_TOOL_NAME,
    COMMAND_KEY,
    COMMENT_RETRY_INSTRUCTION,
    DETAILS_BLOCK_PATTERN,
    GH_COMMENT_COMMAND_PATTERN,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.reply_length_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    HOOK_EVENT_NAME,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)


def comment_body_texts(tool_name: object, all_tool_input: dict[str, object]) -> list[str]:
    """Return the comment bodies one call would post, or an empty list."""
    if tool_name in ALL_CHECKED_MCP_TOOL_NAMES:
        return extract_mcp_body_texts(all_tool_input)
    if tool_name != BASH_TOOL_NAME:
        return []
    command = all_tool_input.get(COMMAND_KEY)
    if not isinstance(command, str) or GH_COMMENT_COMMAND_PATTERN.search(command) is None:
        return []
    all_body_texts, _ = extract_gh_post_body_texts_for_privacy_gate(command)
    return all_body_texts


def comment_violation(comment_text: str) -> str | None:
    """Return the deny reason for an over-long comment, or None when it fits."""
    return length_violation(DETAILS_BLOCK_PATTERN.sub(" ", comment_text))


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    for each_body_text in comment_body_texts(tool_name, tool_input):
        violation = comment_violation(each_body_text)
        if violation is None:
            continue
        block_reason = violation + COMMENT_RETRY_INSTRUCTION
        log_hook_block(
            Path(__file__).name,
            HOOK_EVENT_NAME,
            block_reason,
            tool_name=str(tool_name),
            offending_input_preview=each_body_text,
        )
        sys.stderr.write(block_reason)
        return BLOCK_EXIT_CODE
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
