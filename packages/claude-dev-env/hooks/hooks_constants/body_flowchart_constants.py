import re

FENCE_OPEN_PATTERN: re.Pattern[str] = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(\S*)")
FENCE_MAX_INDENT = 3
FENCE_MARKER_GROUP = 1
INFO_STRING_GROUP = 2
MERMAID_INFO_STRING = "mermaid"
FLOWCHART_FIRST_LINE_PATTERN: re.Pattern[str] = re.compile(r"^flowchart\b")
MERMAID_COMMENT_PREFIX = "%%"
EDGE_LABEL_PATTERN: re.Pattern[str] = re.compile(r"\|[^|]*\|")
NODE_TEXT_PATTERN: re.Pattern[str] = re.compile(r'"[^"]*"|\[[^\]]*\]|\([^)]*\)|\{[^}]*\}')
FLOWCHART_EDGE_PATTERN: re.Pattern[str] = re.compile(
    r"\S.*?(?:<?-->|<?==+>|-\.+->|-\.+-|---+|===+|--[ox])\s*\S"
)
