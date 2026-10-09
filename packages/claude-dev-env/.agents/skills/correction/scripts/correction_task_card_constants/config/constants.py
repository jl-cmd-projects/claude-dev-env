"""Configuration constants for the correction task card command."""

ABSOLUTE_PATH_PATTERN = r"^(?:[/\\~]|[A-Za-z]:)"
BRIEF_KEY = "brief"
ALL_CARD_KEYS = ("title", "tldr", "prompt")
FAILURE_EXIT_CODE = 1
LINE_SEPARATOR = "\n"
FILE_LINE_TEMPLATE = "- `{path}`"
FILES_KEY = "files"
FIX_PLAYBOOK_FILE_NAME = "fix.md"
FIX_PLAYBOOK_FIRST_HANDED_OFF_STEP = "2. "
FIX_PLAYBOOK_DIRECTORY_NAME = "playbooks"
MARKDOWN_LINK_PATTERN = r"\[([^\]]+)\]\([^)]+\)"
MAXIMUM_TITLE_LENGTH = 59
NO_FILES_LINE = "- None named in the session. Step 4 finds them."
PROMPT_TEMPLATE = (
    "Land this correction as one control and one pull request.\n\n"
    "## Correction brief\n\n"
    "{brief}\n\n"
    "## Files, relative to the repository root\n\n"
    "{file_lines}\n\n"
    "## Fix playbook\n\n"
    "The brief above is step 1. Start at step 2.\n\n"
    "{playbook_steps}\n"
)
SUCCESS_EXIT_CODE = 0
TITLE_KEY = "title"
TLDR_KEY = "tldr"
UTF8_ENCODING = "utf-8"
INVALID_INPUT_MESSAGE_TEMPLATE = "Invalid card input: {reason}\n"
REASON_NOT_AN_OBJECT = "standard input must hold one JSON object"
REASON_EMPTY_FIELD_TEMPLATE = "{field} is empty"
REASON_MULTI_LINE_FIELD_TEMPLATE = "{field} must be one line"
REASON_TITLE_TOO_LONG_TEMPLATE = "title has {length} characters; the limit is {limit}"
REASON_FILES_NOT_A_LIST = "files must be a list of strings"
REASON_ABSOLUTE_FILE_TEMPLATE = (
    "{path} is absolute; name it relative to the repository root"
)
