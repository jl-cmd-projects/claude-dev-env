"""Configuration constants for the correction filing command."""

ALL_REDACTION_PATTERNS = (
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)
BODY_FIELD_TEMPLATE = "body={value}"
ALL_SOURCES = ("typed", "flag", "reaction", "hook")
CLAUDE_DIRECTORY_NAME = ".claude"
CONFIG_ENCODING = "utf-8"
CONFIG_FILE_NAME = "correction-capture.json"
CONFIG_LABEL_KEY = "label"
CONFIG_PATH_ENV_VAR = "CLAUDE_CORRECTION_CAPTURE_PATH"
CONFIG_REPOSITORY_KEY = "repository"
CREATED_URL_JQ_FILTER = ".html_url"
DEDUPE_MARKER_PATTERN = r"<!-- correction-dedupe: ([0-9a-f]{16,64}) -->"
DEDUPE_MARKER_TEMPLATE = "<!-- correction-dedupe: {key} -->"
DEDUPE_KEY_LENGTH = 16
DEFAULT_SOURCE = "typed"
DUPLICATE_MESSAGE_TEMPLATE = "Already filed: {url}\n"
EMPTY_TEXT_MESSAGE = "The correction text is empty. Nothing was filed.\n"
FAILURE_EXIT_CODE = 1
FILED_MESSAGE_TEMPLATE = "Filed: {url}\n"
GH_EXECUTABLE = "gh"
ISSUE_BODY_TEMPLATE = (
    "A correction the user made to an agent.\n\n"
    "Source: {source}\n\n"
    "{quoted_text}\n\n"
    "{dedupe_marker}\n"
)
ISSUES_CREATE_PATH_TEMPLATE = "repos/{repository}/issues"
ISSUES_LIST_JQ_FILTER = (
    ".[] | select(.pull_request | not) | {number, title, url: .html_url, body}"
)
ISSUES_LIST_PATH_TEMPLATE = "repos/{repository}/issues?labels={label}&state={state}&per_page=100"
ISSUE_TITLE_PREFIX = "Correction: "
ISSUE_TITLE_TEXT_LENGTH = 72
LABEL_FIELD_TEMPLATE = "labels[]={value}"
LEDGER_FILE_NAME = "correction-capture-filed.json"
LEDGER_KEY_TEMPLATE = "{repository} {dedupe_key}"
LINE_SEPARATOR = "\n"
LIST_LINE_TEMPLATE = "#{number} {title} {url}\n"
MISSING_CONFIG_MESSAGE_TEMPLATE = (
    "No correction filing config at {path}. Write it as "
    '{{"repository": "<owner>/<name>", "label": "<label>"}}. Nothing was filed.\n'
)
NO_OPEN_CORRECTIONS_MESSAGE = "No open corrections.\n"
REDACTION_PLACEHOLDER = "[redacted]"
SUCCESS_EXIT_CODE = 0
TITLE_FIELD_TEMPLATE = "title={value}"
UTF8_ENCODING = "utf-8"
WORD_SEPARATOR = " "
