"""Constants for the wording that says something waits on the user."""

import re

WORD_START = r"(?<![^\W_])"
WORD_END = r"(?![^\W_])"
LINK_TARGET_LIMIT = 256
LINK_TARGET_SPAN = "{0," + str(LINK_TARGET_LIMIT) + "}"
LINK_CLOSER = (
    r"\](?:\([^\s)]" + LINK_TARGET_SPAN + r"\)|\[[^\s\]]" + LINK_TARGET_SPAN + r"\])?"
)
PHRASE_GAP = r"[*_\[]{0,3}(?:" + LINK_CLOSER + r"[*_]{0,3})?\s+[*_\[]{0,3}"
PHRASE_GROUP = "phrase"
USER_STEP_PATTERN = re.compile(
    WORD_START
    + "(?=(?P<" + PHRASE_GROUP + ">"
    + (
        r"(?:needs?\s+your?"
        r"|need(?:ed|s)?\s+from\s+you"
        r"|wait(?:s|ing)?\s+(?:on|for)\s+your?"
        r"|blocked\s+on\s+you"
        r"|you(?:\s+still)?\s+need\s+to"
        r"|you(?:['’]ll|\s+will)\s+need\s+to"
        r"|for\s+you\s+to\s+(?:do|run|merge|approve|add|paste|click|decide|confirm|archive|sign|set)"
        r"|(?:let\s+me\s+know|tell\s+me|say)\s+when"
        r"|action\s+(?:needed|required))"
    ).replace(r"\s+", PHRASE_GAP)
    + WORD_END
    + "))",
    re.IGNORECASE,
)
CLAUSE_WORD_PATTERN = re.compile(r"(?<!\S)\S+")
WORD_RUN_PATTERN = re.compile(r"\S+")
EMPHASIS_MARKS = "*_"
MARKER_WORD_PATTERN = re.compile(r"[-+#>\d)(\[\]]*")
ALL_ABSENCE_WORDS = frozenset({"nothing", "none", "nobody"})
ALL_CLAUSE_OPENING_NEGATORS = frozenset({"no", "neither", "nor"})
THERE_WORD = "there"
ALL_THERE_VERBS = frozenset({"is", "are", "was", "were"})
ALL_LATE_NEGATORS = frozenset({"not", "never", "without"})
ALL_CONTRACTED_NEGATOR_ENDINGS = ("n't", "n’t")
ALL_NO_LONGER_WORDS = ("no", "longer")
MAXIMUM_WORDS_AFTER_LATE_NEGATOR = 3
NEGATED_TAIL_PATTERN = re.compile(
    r"(?:[^\S\n]|[*_]){0,8}[:\-–—](?:[^\S\n]|[*_]){0,8}"
    r"(?:none|nothing|n/a|no[^\S\n]+(?:action|step)s?)"
    r"(?:[^\S\n]+(?:needed|required|for[^\S\n]+now|at[^\S\n]+this[^\S\n]+time|right[^\S\n]+now))?"
    r"[*_]{0,3}[.!?]?[*_]{0,3}[^\S\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
CLAUSE_BREAK_PATTERN = re.compile(r"[.!?,;:|\n]|\b(?:and|but|so|then|while)\b", re.IGNORECASE)
LINE_BREAK = "\n"
LINE_ENDING_PATTERN = re.compile(r"\r\n?")
ODD_LINE_END_PATTERN = re.compile(r"[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")
CODE_SPAN_STAND_IN = "\ufffc"
CODE_SPAN_SPACE = " "
HTML_LITERAL_STAND_IN_TEXT = "\ufffd"
CLAUSE_LEAD_WINDOW_CHARACTERS = 240
BARE_IMPERATIVE_PATTERN = re.compile(r"say\s", re.IGNORECASE)
OPENER_MARKER_CHARACTERS = "-+#>.)([]*_0123456789"
ALL_INSTRUCTION_OPENERS = frozenset({(), ("please",), ("just",), ("please", "just")})
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
ALL_HTML_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
HTML_SOURCE_SPACE_PATTERN = re.compile(r"[ \t\r\n\f]+")
HTML_SOURCE_SPACE = " "
HTML_BLOCK_SEPARATOR = "\n\n"
ALL_HTML_FILE_SUFFIXES = frozenset({".html", ".htm"})
ALL_SENT_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt"}) | ALL_HTML_FILE_SUFFIXES
MAXIMUM_SENT_FILE_BYTES = 262144
BINARY_READ_MODE = "rb"
