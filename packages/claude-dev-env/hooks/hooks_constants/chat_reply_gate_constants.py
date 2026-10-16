"""Constants for the chat reply gate UserPromptSubmit and MessageDisplay hook."""

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)

HOOK_EVENT_NAME_INPUT_KEY = "hook_event_name"
MESSAGE_DISPLAY_EVENT_NAME = "MessageDisplay"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
SESSION_END_EVENT_NAME = "SessionEnd"
SESSION_ID_KEY = "session_id"
MESSAGE_ID_KEY = "message_id"
DELTA_KEY = "delta"
FINAL_KEY = "final"
DISPLAY_CONTENT_KEY = "displayContent"
STATE_FILE_ENCODING = "utf-8"
HELD_TEXT_FILE_PREFIX = "claude-chat-reply-held-"
SHOWN_DRAFT_FILE_PREFIX = "claude-chat-reply-shown-"
STATE_FILE_SUFFIX = ".txt"
REPLY_LIMIT_REMINDER = (
    f"Your reply to the user is final and gets no second pass. Keep it to {MAXIMUM_SENTENCE_COUNT}"
    f" sentences or fewer, each {MAXIMUM_WORDS_PER_SENTENCE} words or fewer."
    " Each line and each list item counts as one sentence, so prefer short prose over lists."
    " Lead with the outcome and cut detail the user did not ask for."
    " No colon in the middle of a sentence, and no em dash."
    " Put any pull request number inside a markdown link."
    " A sentence with so, because, caused, due to, therefore, or means needs inline code, a URL, or a link in it."
    " Never write real, really, genuine, actual, actually, likely, probably, seems, maybe, perhaps, may be, or might be."
    " Count your sentences before you send."
)
SHOWN_DRAFT_PREFIX = "\n\nThe user saw your last reply condensed to this text, so build on it:\n\n"
DRAFTER_GUARD_ENV_VAR = "CHAT_REPLY_DRAFTER_ACTIVE"
DRAFTER_MODEL_ENV_VAR = "CHAT_REPLY_DRAFTER_MODEL"
DEFAULT_DRAFTER_MODEL = "haiku"
DRAFTER_TIMEOUT_SECONDS = 45
MAXIMUM_DRAFT_ATTEMPTS = 2
DRAFTER_RESULT_KEY = "result"
DRAFTER_ERROR_KEY = "is_error"
DRAFTER_EXECUTABLE_NAME = "claude"
CLAUDE_SESSION_ID_ENV_VAR = "CLAUDE_CODE_SESSION_ID"
DRAFTER_REQUEST_TEMPLATE = "Rule the reply broke: {violation}\n\nReply to rewrite:\n\n{reply_text}"
DRAFTER_RULES = (
    f"Rewrite the reply below so it obeys every rule. At most {MAXIMUM_SENTENCE_COUNT} sentences,"
    f" each at most {MAXIMUM_WORDS_PER_SENTENCE} words. Each line and each list item counts as one sentence."
    " Keep the outcome, the recommendation, and any number, path, or command the user needs."
    " Drop background the user did not ask for."
    " No colon in the middle of a sentence. No em dash."
    " Write a pull request number only inside a markdown link."
    " A sentence that gives a cause, with so, because, caused, due to, therefore, or means,"
    " must hold its own evidence as inline code, a URL, or a markdown link. Otherwise state the fact without the cause word."
    " Never use these words: real, really, genuine, actual, actually, likely, probably, seems, maybe, perhaps,"
    " might be, may be, appears to, suspect, guess, presumably."
    " Speak as the original author to the original reader."
    " Never mention the rule, the length, or this rewrite."
    " Never add, drop, or change a fact, a command, a flag, or a file name; leave out a whole point instead."
    " Return only the rewritten reply, with no preface."
)
