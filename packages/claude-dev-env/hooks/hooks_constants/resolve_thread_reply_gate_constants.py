"""Constants for the gate that holds a review thread resolve until a reply on it posts."""

import re

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)

RESOLVE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__resolve_review_thread$")
ALL_REPLY_TOOL_NAME_SUFFIXES = ("__add_reply_to_pull_request_comment",)
SHELL_COMMAND_KEY = "command"
SHELL_REPLY_COMMAND_PATTERN = re.compile(
    r"\bgh\s+api\b.*(?:/comments/\d+/replies\b|addPullRequestReviewThreadReply)", re.DOTALL
)
MISSING_REPLY_REASON = (
    "This review thread has no reply that posted since the last user prompt and the last resolve."
    " Post the reply with add_reply_to_pull_request_comment, confirm its result came back without"
    " an error, then resolve the thread. A reply that a hook refused did not post; shorten it to"
    f" at most {MAXIMUM_SENTENCE_COUNT} sentences of at most {MAXIMUM_WORDS_PER_SENTENCE} words each,"
    " footer included, and send it again."
)
