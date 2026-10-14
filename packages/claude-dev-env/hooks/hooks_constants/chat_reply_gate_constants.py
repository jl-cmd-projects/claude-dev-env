"""Constants for the chat reply gate Stop and UserPromptSubmit hook."""

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)

HOOK_EVENT_NAME_INPUT_KEY = "hook_event_name"
STOP_EVENT_NAME = "Stop"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
SESSION_END_EVENT_NAME = "SessionEnd"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
SESSION_ID_KEY = "session_id"
MAXIMUM_REWRITES_PER_TURN = 3
REWRITE_COUNT_FILE_PREFIX = "claude-chat-reply-rewrites-"
REWRITE_COUNT_FILE_SUFFIX = ".txt"
REWRITE_COUNT_ENCODING = "utf-8"
REWRITE_INSTRUCTION = (
    " Rewrite the reply in plain words, like one person talking to another,"
    " and write it out again as plain chat text."
    " Cut detail the user did not ask for."
)
REPLY_LIMIT_REMINDER = (
    f"Keep your reply to the user to {MAXIMUM_SENTENCE_COUNT} sentences or fewer,"
    f" each {MAXIMUM_WORDS_PER_SENTENCE} words or fewer, in plain words."
    " Each line and each list item counts as one sentence."
    " Lead with the outcome and cut detail the user did not ask for."
    " When the turn ends, a longer reply goes back to you for a rewrite."
)
