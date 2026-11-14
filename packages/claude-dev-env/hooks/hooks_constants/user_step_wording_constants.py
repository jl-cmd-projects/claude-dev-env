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
NEGATING_WORD_PATTERN = re.compile(
    r"\b(?:nothing|none|no|not|never|neither|nor|without)\b|n['’]t\b", re.IGNORECASE
)
CLAUSE_BREAK_PATTERN = re.compile(r"[.!?\n,;:]|\b(?:and|but|so|then|while)\b", re.IGNORECASE)
CLAUSE_LEAD_WINDOW_CHARACTERS = 240
ALL_HTML_HIDDEN_TAGS = frozenset({"script", "style", "template", "code", "pre", "blockquote"})
ALL_HTML_INLINE_TAGS = frozenset(
    {"a", "abbr", "b", "cite", "em", "font", "i", "kbd", "label", "mark", "q", "s", "small", "span", "strong", "sub", "sup", "u", "var"}
)
HTML_BLOCK_SEPARATOR = "\n"
ALL_HTML_FILE_SUFFIXES = frozenset({".html", ".htm"})
ALL_SENT_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt"}) | ALL_HTML_FILE_SUFFIXES
MAXIMUM_SENT_FILE_BYTES = 262144
BINARY_READ_MODE = "rb"
