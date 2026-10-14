"""Constants for the chat reply gate Stop and UserPromptSubmit hook."""

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)

HOOK_EVENT_NAME_INPUT_KEY = "hook_event_name"
STOP_EVENT_NAME = "Stop"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
SESSION_ID_KEY = "session_id"
MAXIMUM_REWRITES_PER_TURN = 3
REWRITE_COUNT_FILE_PREFIX = "claude-chat-reply-rewrites-"
REWRITE_COUNT_FILE_SUFFIX = ".txt"
REWRITE_COUNT_ENCODING = "utf-8"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
REWRITE_INSTRUCTION = (
    " Rewrite the reply in plain words, like one person talking to another, and send it again."
    " Cut detail the user did not ask for."
)
REPLY_LIMIT_REMINDER = (
    f"Keep your reply to the user to {MAXIMUM_SENTENCE_COUNT} sentences or fewer,"
    f" each {MAXIMUM_WORDS_PER_SENTENCE} words or fewer, in plain words."
    " Each line and each list item counts as one sentence."
    " Lead with the outcome and cut detail the user did not ask for."
    " When the turn ends, a longer reply goes back to you for a rewrite."
)
