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
    "address", "article", "aside", "base", "basefont", "blockquote", "body", "caption", "center",
    "col", "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt", "fieldset",
    "figcaption", "figure", "footer", "form", "frame", "frameset", "h1", "h2", "h3", "h4", "h5",
    "h6", "head", "header", "hr", "html", "iframe", "legend", "li", "link", "main", "menu",
    "menuitem", "nav", "noframes", "ol", "optgroup", "option", "p", "param", "search", "section",
    "summary", "table", "tbody", "td", "tfoot", "th", "thead", "title", "tr", "track", "ul",
)
HTML_BLOCK_OPENER_PATTERN = re.compile(
    r"^ {0,3}(?:"
    r"(?P<raw><(?:pre|script|style|textarea)(?:[\s>]|$))"
    r"|(?P<comment><!--)"
    r"|(?P<instruction><\?)"
    r"|(?P<cdata><!\[CDATA\[)"
    r"|(?P<declaration><![A-Za-z])"
    r"|(?P<block></?(?:" + "|".join(ALL_HTML_BLOCK_TAG_NAMES) + r")(?:[\s>]|/>|$))"
    r")",
    re.IGNORECASE | re.MULTILINE,
)
ALL_HTML_BLOCK_CLOSER_PATTERNS = {
    "raw": re.compile(r"</(?:pre|script|style|textarea)>[^\n]*", re.IGNORECASE),
    "comment": re.compile(r"-->[^\n]*"),
    "instruction": re.compile(r"\?>[^\n]*"),
    "cdata": re.compile(r"\]\]>[^\n]*"),
    "declaration": re.compile(r">[^\n]*"),
    "block": re.compile(r"(?=\n[ \t]*\n)|\Z"),
}
BLOCK_BOUNDARY_PATTERN = re.compile(r"\n[ \t]*\n|\n(?= {0,3}(?:[-*+]|1[.)])[ \t]+\S)")
QUOTE_MARKER_PATTERN = re.compile(r"(?: {0,3}>[ \t]?)*")
QUOTE_MARKER = ">"
MASKED_BLOCK_TEXT = "\n\n"
HEADING_LINE_PATTERN = re.compile(
    r"^( {0,3}(?:#{1,6}(?:[ \t][^\n]*)?|=+[ \t]*|(?:-[ \t]*)+|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}))$",
    re.MULTILINE,
)
HEADING_AS_OWN_BLOCK = "\n\n\\1\n\n"
PARAGRAPH_SEPARATOR = "\n\n"
BACKSLASH = "\\"
BACKSLASHES_PER_LITERAL = 2
MASKED_CODE_TEXT = " "
FENCE_OPENER_PATTERN = re.compile(r"^ {0,3}(?:(`{3,})[^`\n]*|(~{3,})[^\n]*)\n", re.MULTILINE)
FENCE_CLOSER_PREFIX = r"^ {0,3}"
FENCE_CLOSER_SUFFIX = r"*[ \t]*$"
WINDOWS_PATH_MESSAGE = (
    'Path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
