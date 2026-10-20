"""Constants for the final reply gate Stop hook."""

import re

HOOK_EVENT_NAME = "Stop"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
TRANSCRIPT_PATH_KEY = "transcript_path"
DECISION_KEY = "decision"
BLOCK_DECISION = "block"
REASON_KEY = "reason"
ALLOW_EXIT_CODE = 0
REWRITE_INSTRUCTION = " Rewrite the reply without it."
NON_SPACE_TOKEN_PATTERN = re.compile(r"\S+")
ESCAPED_PUNCTUATION_PATTERN = re.compile(r"(?<!\\)(?:\\\\)*\\[!-/:-@\[\]^_`{-~]")
HARD_BREAK_PATTERN = re.compile(r"(?<!\\)(?:\\\\)*\\\Z")
CARRIAGE_RETURN_LINE_BREAK = "\r\n"
LINE_BREAK = "\n"
BACKTICK_RUN_PATTERN = re.compile(r"`+")
ALL_HTML_BLOCK_TAG_NAMES = (
    "address article aside base basefont blockquote body caption center col colgroup"
    " dd details dialog dir div dl dt fieldset figcaption figure footer form frame"
    " frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu"
    " menuitem nav noframes ol optgroup option p param search section summary table"
    " tbody td tfoot th thead title tr track ul"
).split()
HTML_BLOCK_START = (
    r"<(?:!--|\?|![A-Za-z]|!\[CDATA\[|(?:pre|script|style|textarea)(?:[\s>]|$)"
    r"|/?(?:" + "|".join(ALL_HTML_BLOCK_TAG_NAMES) + r")(?:[\s>]|/>|$))"
)
BLOCK_BOUNDARY_PATTERN = re.compile(
    r"\n[ \t]*\n|\n(?= {0,3}(?:(?:[-*+]|1[.)])[ \t]+\S|>|" + HTML_BLOCK_START + "))",
    re.IGNORECASE,
)
HEADING_LINE_PATTERN = re.compile(
    r"^( {0,3}(?:#{1,6}(?:[ \t][^\n]*)?|=+[ \t]*|(?:-[ \t]*)+|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}))$",
    re.MULTILINE,
)
HEADING_AS_OWN_BLOCK = "\n\n\\1\n\n"
PARAGRAPH_SEPARATOR = "\n\n"
BACKSLASH = "\\"
BACKSLASHES_PER_LITERAL = 2
MASKED_CODE_TEXT = " "
FENCED_CODE_PATTERN = re.compile(
    r"^ {0,3}(?:(`{3,})[^`\n]*|(~{3,})[^\n]*)\n.*?(?:^ {0,3}(?:\1`*|\2~*)[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
WINDOWS_PATH_MESSAGE = (
    'Path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
