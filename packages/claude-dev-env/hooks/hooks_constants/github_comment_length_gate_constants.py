"""Constants for the GitHub comment length gate PreToolUse hook."""

import re

ALL_CHECKED_MCP_TOOL_NAMES = frozenset(
    {
        "mcp__github__add_issue_comment",
        "mcp__github__update_issue_comment",
        "mcp__github__add_reply_to_pull_request_comment",
        "mcp__github__add_comment_to_pending_review",
        "mcp__github__pull_request_review_write",
    }
)
BASH_TOOL_NAME = "Bash"
COMMAND_KEY = "command"
GH_COMMENT_COMMAND_PATTERN = re.compile(r"\bgh\s+(?:pr|issue)\s+(?:comment|review)\b")
DETAILS_BLOCK_PATTERN = re.compile(r"<details\b.*?</details>", re.IGNORECASE | re.DOTALL)
COMMENT_RETRY_INSTRUCTION = (
    " A GitHub comment holds at most three short sentences."
    " Put detail in the pull request body, a code block, or a collapsed <details> block, then post again."
)
