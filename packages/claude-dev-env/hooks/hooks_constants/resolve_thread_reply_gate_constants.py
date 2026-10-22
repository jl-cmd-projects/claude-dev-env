"""Constants for the gate that holds a review thread resolve until a reply on it posts."""

import re

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)

RESOLVE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__resolve_review_thread$")
REVIEW_WRITE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__pull_request_review_write$")
REVIEW_WRITE_METHOD_KEY = "method"
RESOLVE_THREAD_METHOD = "resolve_thread"
ALL_REPLY_TOOL_NAME_SUFFIXES = ("__add_reply_to_pull_request_comment",)
SHELL_COMMAND_KEY = "command"
SHELL_REPLY_COMMAND_PATTERN = re.compile(
    r"\bgh\s+api\b.*(?:/comments/\d+/replies\b|addPullRequestReviewThreadReply)", re.DOTALL
)
SHELL_RESOLVE_COMMAND_PATTERN = re.compile(r"\bgh\s+api\s+graphql\b.*\bresolveReviewThread\b", re.DOTALL)
SHELL_RESOLVE_COMMENT_ID_PATTERN = re.compile(r"/pulls/\d+/ccr/comments/(\d+)/resolve\b")
ALL_THREAD_ID_INPUT_KEYS = ("threadID", "threadId")
COMMENT_ID_INPUT_KEY = "commentId"
THREAD_ID_PATTERN = re.compile(r"\bPRRT_[A-Za-z0-9_-]+")
COMMENT_ANCHOR_PATTERN = re.compile(r"(?:discussion_r|\"databaseId\"\s*:\s*)(\d+)")
SHELL_REPLY_COMMENT_ID_PATTERN = re.compile(r"/comments/(\d+)/replies\b")
TEXT_BLOCK_TYPE = "text"
TEXT_FIELD = "text"
MISSING_REPLY_REASON = (
    "This review thread has no reply on it that posted since the last user prompt and the last"
    " resolve of the thread. Post the reply on this thread with add_reply_to_pull_request_comment,"
    " or with gh api graphql addPullRequestReviewThreadReply and the thread's PRRT_ id, confirm its"
    " result came back without an error, then resolve the thread by its PRRT_ id or by the comment id the reply answered. A comment id"
    " ties to a thread only through a pull_request_read get_review_comments result in this session."
    " A reply that a hook refused did not post; shorten it to"
    f" at most {MAXIMUM_SENTENCE_COUNT} sentences of at most {MAXIMUM_WORDS_PER_SENTENCE} words each,"
    " footer included, and send it again."
)
