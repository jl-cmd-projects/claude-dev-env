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
NEGATED_LEAD_PATTERN = re.compile(
    r"(?:\b(?:nothing|none|no|not|never|neither|without)\b|n['’]t\b)(?:\s+[\w-]+){0,3}\s*$",
    re.IGNORECASE,
)
SENTENCE_BREAK_PATTERN = re.compile(r"[.!?\n]")
HTML_HIDDEN_BLOCK_PATTERN = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
HTML_TAG_REPLACEMENT = "\n"
ALL_HTML_FILE_SUFFIXES = frozenset({".html", ".htm"})
ALL_SENT_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt"}) | ALL_HTML_FILE_SUFFIXES
MAXIMUM_SENT_FILE_BYTES = 262144
SENT_FILE_DECODE_ERRORS = "replace"
