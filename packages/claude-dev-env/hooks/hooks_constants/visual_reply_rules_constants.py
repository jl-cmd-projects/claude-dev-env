"""Constants for the visual reply mode checks in the reply length gate."""

import re
from pathlib import Path

RULES_FILE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "rules" / "visual-reply-rules.json"
)
RULES_FILE_ENCODING = "utf-8"
RULES_LIST_KEY = "rules"
RULE_KEY_FIELD = "key"
RULE_LABEL_FIELD = "label"
RULE_REMINDER_FIELD = "reminder"
ALLOWED_CAPITALIZED_WORDS_KEY = "allowed_capitalized_words"
LOWERCASE_ABBREVIATIONS_KEY = "lowercase_abbreviations"

MODE_SWITCH_FILE_NAME = "visual-reply-mode.json"
MODE_SWITCH_ENABLED_KEY = "enabled"

NO_PICTURE_RULE_KEY = "no_picture"
ABBREVIATIONS_RULE_KEY = "abbreviations"
ONE_ITEM_RULE_KEY = "one_item"

WIDGET_TOOL_NAME_SUFFIX = "__post_widget"
ARTIFACT_TOOL_NAME = "Artifact"
ALL_VISUAL_TOOL_NAME_SUFFIXES = (WIDGET_TOOL_NAME_SUFFIX, ARTIFACT_TOOL_NAME)
ALL_REPLY_TOOL_NAME_SUFFIXES = ("__reply", "__post_message")
MAXIMUM_REPLIES_PER_TURN = 1
MAXIMUM_SENTENCES_WITHOUT_VISUAL = 1

CAPITALIZED_ABBREVIATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?=[A-Z0-9]*[A-Z][A-Z0-9]*[A-Z])[A-Z0-9]{2,}s?(?![A-Za-z0-9])"
)
LOWERCASE_ABBREVIATION_TEMPLATE = r"(?<![A-Za-z0-9]){abbreviation}(?![A-Za-z0-9])"
TRACKER_NUMBER_PATTERN = re.compile(
    r"\b(?:issues?|items?|cards?|tickets?|tasks?)\s*#?\d+", re.IGNORECASE
)
WIDGET_ANCHOR_PATTERN = re.compile(r"<a\b[^>]*\bhref\s*=", re.IGNORECASE)

TRANSCRIPT_ENCODING = "utf-8"
ENTRY_TYPE_KEY = "type"
USER_ENTRY_TYPE = "user"
ASSISTANT_ENTRY_TYPE = "assistant"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
BLOCK_TYPE_KEY = "type"
BLOCK_NAME_KEY = "name"
TEXT_BLOCK_TYPE = "text"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
BLOCK_ID_KEY = "id"
TOOL_USE_ID_KEY = "tool_use_id"
IS_ERROR_KEY = "is_error"
IS_META_KEY = "isMeta"

ABBREVIATION_MESSAGE = 'Abbreviation "{abbreviation}" in the text. {reminder}'
TRACKER_NUMBER_MESSAGE = 'Tracker number "{reference}" in the text. {reminder}'
NO_VISUAL_MESSAGE = "This reply has {sentence_count} sentences and no visual this turn. {reminder}"
SECOND_REPLY_MESSAGE = "A reply already went out this turn. {reminder}"
WIDGET_ANCHOR_MESSAGE = (
    "A link sits inside the widget code, and a widget link does not open in the Claude app."
    " Remove the anchor and put the page link in the reply text."
)
