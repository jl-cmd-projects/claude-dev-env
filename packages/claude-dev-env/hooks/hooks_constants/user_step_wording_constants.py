"""Constants for the wording that says something waits on the user."""

import re

WORD_START = r"(?<![^\W_])"
WORD_END = r"(?![^\W_])"
USER_STEP_PATTERN = re.compile(
    WORD_START
    + r"(?:needs?\s+your?"
    r"|need(?:ed|s)?\s+from\s+you"
    r"|wait(?:s|ing)?\s+(?:on|for)\s+your?"
    r"|blocked\s+on\s+you"
    r"|you(?:\s+still)?\s+need\s+to"
    r"|you(?:['’]ll|\s+will)\s+need\s+to"
    r"|for\s+you\s+to\s+(?:do|run|merge|approve|add|paste|click|decide|confirm|archive|sign|set)"
    r"|(?:let\s+me\s+know|tell\s+me|say)\s+when"
    r"|action\s+(?:needed|required))" + WORD_END,
    re.IGNORECASE,
)
CLAUSE_MARKERS = r"[\s\-*+#>\d.)(\[\]_]*"
CLAUSE_WORD_START = r"(?<![\w*-])\**"
CLAUSE_WORD_END = r"\**(?![\w*-])"
NEGATED_CLAUSE_PATTERN = re.compile(
    CLAUSE_WORD_START
    + r"(?:nothing|none|nobody)"
    + CLAUSE_WORD_END
    + r"|(?:"
    + CLAUSE_WORD_START
    + r"(?:not|never|without|no\s+longer)|n['’]t)"
    + CLAUSE_WORD_END
    + r"(?:\s+[\w*'’-]+){0,3}\s*$",
    re.IGNORECASE,
)
NEGATED_CLAUSE_START_PATTERN = re.compile(
    CLAUSE_MARKERS + r"(?:there\s+(?:is|are|was|were)\s+)?(?:no|neither|nor)" + CLAUSE_WORD_END,
    re.IGNORECASE,
)
NEGATED_TAIL_PATTERN = re.compile(
    r"(?:[^\S\n]|[*_]){0,8}[:\-–—](?:[^\S\n]|[*_]){0,8}"
    r"(?:none|nothing|n/a|no[^\S\n]+(?:action|step)s?)"
    r"(?:[^\S\n]+(?:needed|required|for[^\S\n]+now|at[^\S\n]+this[^\S\n]+time|right[^\S\n]+now))?"
    r"[*_]{0,3}[.!?]?[*_]{0,3}[^\S\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
CLAUSE_BREAK_PATTERN = re.compile(
    r"[.!?,;:|\n]|" + CLAUSE_WORD_START + r"(?:and|but|so|then|while)" + CLAUSE_WORD_END, re.IGNORECASE
)
LINE_BREAK = "\n"
CLAUSE_LEAD_WINDOW_CHARACTERS = 240
BARE_IMPERATIVE_PATTERN = re.compile(r"say\s", re.IGNORECASE)
CLAUSE_OPENER_PATTERN = re.compile(CLAUSE_MARKERS + r"(?:please\s+)?(?:just\s+)?", re.IGNORECASE)
ALL_HTML_HIDDEN_TAGS = frozenset(
    {"script", "style", "template", "title", "textarea", "noscript", "code", "pre", "blockquote"}
)
ALL_HTML_INLINE_TAGS = frozenset(
    {
        "a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn", "em", "font", "i", "img",
        "ins", "kbd", "label", "mark", "q", "s", "samp", "small", "span", "strike", "strong", "sub", "sup",
        "time", "tt", "u", "var", "wbr",
    }
)
HTML_LINE_BREAK_TAG = "br"
HTML_LINE_BREAK_TEXT = LINE_BREAK
HTML_SOURCE_SPACE_PATTERN = re.compile(r"[ \t\r\n\f]+")
HTML_SOURCE_SPACE = " "
HTML_BLOCK_SEPARATOR = "\n\n"
ALL_HTML_FILE_SUFFIXES = frozenset({".html", ".htm"})
ALL_SENT_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt"}) | ALL_HTML_FILE_SUFFIXES
MAXIMUM_SENT_FILE_BYTES = 262144
BINARY_READ_MODE = "rb"
