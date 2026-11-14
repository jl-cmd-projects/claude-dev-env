"""Constants for the wording that says something waits on the user."""

import re

USER_STEP_PATTERN = re.compile(
    r"\bneeds?\s+your?\b"
    r"|\bneed(?:ed|s)?\s+from\s+you\b"
    r"|\bwait(?:s|ing)?\s+(?:on|for)\s+your?\b"
    r"|\bblocked\s+on\s+you\b"
    r"|\byou(?:\s+still)?\s+need\s+to\b"
    r"|\byou(?:['’]ll|\s+will)\s+need\s+to\b"
    r"|\bfor\s+you\s+to\s+(?:do|run|merge|approve|add|paste|click|decide|confirm|archive|sign|set)\b"
    r"|\b(?:let\s+me\s+know|tell\s+me|say)\s+when\b"
    r"|\baction\s+(?:needed|required)\b",
    re.IGNORECASE,
)
NEGATED_CLAUSE_PATTERN = re.compile(
    r"\b(?:nothing|none|nobody)\b"
    r"|^\s*(?:there\s+(?:is|are|was|were)\s+)?(?:no|neither|nor)\b"
    r"|(?:\b(?:not|never|without|no\s+longer)|n['’]t)(?:\s+[\w-]+){0,3}\s*$",
    re.IGNORECASE,
)
NEGATED_TAIL_PATTERN = re.compile(r"[\s*_]*[:\-–—]?[\s*_]*(?:none|nothing|no|n/a)(?![a-z0-9])", re.IGNORECASE)
CLAUSE_BREAK_PATTERN = re.compile(
    r"[.!?,;:|]|\n\s*\n|\n\s*[-*+#]+\s|\b(?:and|but|so|then|while)\b", re.IGNORECASE
)
CLAUSE_LEAD_WINDOW_CHARACTERS = 240
PHRASE_TAIL_WINDOW_CHARACTERS = 16
BARE_IMPERATIVE_PATTERN = re.compile(r"say\s", re.IGNORECASE)
CLAUSE_OPENER_PATTERN = re.compile(r"[\s\-*+#>\d.)]*(?:please|just)?\s*", re.IGNORECASE)
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
HTML_LINE_BREAK_TEXT = " "
HTML_BLOCK_SEPARATOR = "\n\n"
ALL_HTML_FILE_SUFFIXES = frozenset({".html", ".htm"})
ALL_SENT_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt"}) | ALL_HTML_FILE_SUFFIXES
MAXIMUM_SENT_FILE_BYTES = 262144
BINARY_READ_MODE = "rb"
