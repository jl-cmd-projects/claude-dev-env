import re

FENCE_OPEN_PATTERN: re.Pattern[str] = re.compile(r"^\s*(`{3,}|~{3,})[ \t]*(\S*)(.*)$")
MINIMUM_FENCE_LENGTH = 3
FENCE_MARKER_GROUP = 1
INFO_STRING_GROUP = 2
INFO_TAIL_GROUP = 3
BACKTICK_FENCE_CHARACTER = "`"
FRONT_MATTER_DELIMITER = "---"
MERMAID_INFO_STRING = "mermaid"
FLOWCHART_FIRST_LINE_PATTERN: re.Pattern[str] = re.compile(r"^flowchart\b")
MERMAID_COMMENT_PREFIX = "%%"
TRAILING_COMMENT_PATTERN: re.Pattern[str] = re.compile(r"%%.*$")
EDGE_LABEL_PATTERN: re.Pattern[str] = re.compile(r"\|[^|]*\|")
NODE_TEXT_PATTERN: re.Pattern[str] = re.compile(r'"[^"]*"|\[[^\]]*\]|\([^)]*\)|\{[^}]*\}')
FLOWCHART_EDGE_PATTERN: re.Pattern[str] = re.compile(
    r"\S.*?(?:<?-->|<?==+>|-\.+->|-\.+-|---+|===+|--[ox])\s*\S"
)
