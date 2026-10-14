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
MAXIMUM_REWRITES_PER_TURN = 1
REWRITE_COUNT_FILE_PREFIX = "claude-chat-reply-rewrites-"
REWRITE_COUNT_FILE_SUFFIX = ".txt"
REWRITE_COUNT_ENCODING = "utf-8"
REWRITE_INSTRUCTION = (
    " Send only the corrected reply as plain chat text, with no apology, preface,"
    " or mention of this check."
    f" It must pass every rule at once. At most {MAXIMUM_SENTENCE_COUNT} sentences,"
    f" each at most {MAXIMUM_WORDS_PER_SENTENCE} words, one per line or list item."
    " No colon with text after it on the same line. No em dash."
    " Each pull request as a markdown link."
    " Inline code or a link in any sentence that names a cause. No banned word."
)
REPLY_LIMIT_REMINDER = (
    "A checker reads your final reply to the user. A reply that breaks a rule comes back"
    " for a rewrite, and the user sees both replies. Write it once, within these rules:\n"
    f"- At most {MAXIMUM_SENTENCE_COUNT} sentences, each at most {MAXIMUM_WORDS_PER_SENTENCE} words,"
    " so aim for 12. Each line and each list item counts as one sentence."
    " Start list items with a dash, not a number.\n"
    "- No colon with more text after it on the same line.\n"
    "- No em dash. Use a period or a comma.\n"
    "- Write each pull request as a markdown link, never a bare number or #N.\n"
    "- A sentence with because, so, due to, caused, therefore, or which means needs inline"
    " code, a URL, or a link in that same sentence. Otherwise state the fact with no cause word.\n"
    "- Never use these words: {banned_words}.\n"
    "Lead with the outcome the user asked for and cut the rest."
)
