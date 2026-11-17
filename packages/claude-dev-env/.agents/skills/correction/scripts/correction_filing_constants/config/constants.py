"""Configuration constants for the correction filing command."""

ACCOUNT_NAME_MINIMUM_LENGTH = 3
ACCOUNT_NAME_PATTERN_TEMPLATE = r"(?<![\w-]){name}(?![\w-])"
ALL_ACCOUNT_NAME_ENV_VARS = ("USERNAME", "USER")
ALL_GH_COMMAND_PARTS = ("gh",)
ALL_POST_LINT_PATH_PARTS = ("scripts", "durable_post_lint.py")
ALL_PUBLIC_REDACTION_PATTERNS = (
    r"\b[A-Za-z]:[\\/][^\s`'\"<>|]*",
    r"(?:[\\/](?:home|Users)|~)[\\/][^\s`'\"<>|]*",
)
ALL_REDACTION_PATTERNS = (
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)
ALL_SOURCES = ("typed", "flag", "reaction", "hook")
BODY_FIELD_TEMPLATE = "body={value}"
CLAUDE_DIRECTORY_NAME = ".claude"
CONFIG_ENCODING = "utf-8"
CONFIG_FILE_NAME = "correction-capture.json"
CONFIG_PATH_ENV_VAR = "CLAUDE_CORRECTION_CAPTURE_PATH"
CONFIG_REPOSITORY_KEY = "repository"
CORRECTION_LABEL = "correction"
CORRECTION_LINE_PATTERN = r"^Correction:[ \t]*(.+)$"
CREATED_URL_JQ_FILTER = ".html_url"
DEDUPE_KEY_LENGTH = 16
DEDUPE_MARKER_PATTERN = r"<!-- correction-dedupe: ([0-9a-f]{16,64}) -->"
DEDUPE_MARKER_TEMPLATE = "<!-- correction-dedupe: {key} -->"
DEFAULT_SOURCE = "typed"
DUPLICATE_MESSAGE_TEMPLATE = "Already filed: {url}{note}\n"
EMPTY_TEXT_MESSAGE = "The correction text is empty. Nothing was filed.\n"
FAILURE_EXIT_CODE = 1
FALLBACK_NOTE_TEMPLATE = " (fallback: {reasons}; filed on the correction inbox {inbox})"
FILED_MESSAGE_TEMPLATE = "Filed: {url}{note}\n"
FILED_REPEAT_MESSAGE_TEMPLATE = "Filed: {url}, a repeat of {earlier_url}{note}\n"
GIT_EXECUTABLE = "git"
GITHUB_ORIGIN_PATTERN = (
    r"^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$"
)
GITHUB_URL_PATTERN = r"https?://github\.com/([^/\s)>\]]+/[^/\s)>\]#?]+)[^\s)>\]]*"
ISSUE_BODY_TEMPLATE = (
    "{preamble}"
    "## Correction\n\n"
    "The user corrected an agent's work in this repository. The agent fixed the "
    "instance in front of it and posted this issue so the lesson gets fixed on "
    "purpose. Whoever picks it up chooses the layer with the correction lens guide "
    "(`docs/rule-guides/correction-lens.md` in claude-dev-env), lands the control, "
    "and closes this issue from that change.\n\n"
    "Source: {source}\n"
    "{repeat_line}\n"
    "{quoted_text}\n\n"
    "{dedupe_marker}\n"
    "{occurrence_marker}\n"
)
ISSUE_COMMENTS_PATH_TEMPLATE = "repos/{repository}/issues/{number}/comments"
ISSUE_TITLE_PREFIX = "Correction: "
ISSUE_TITLE_TEXT_LENGTH = 72
ISSUES_CREATE_PATH_TEMPLATE = "repos/{repository}/issues"
ISSUES_LIST_JQ_FILTER = (
    ".[] | select(.pull_request | not) | {number, title, url: .html_url, body, state}"
)
ISSUES_LIST_PATH_TEMPLATE = "repos/{repository}/issues?labels={label}&state={state}&per_page=100"
LABEL_COLOR = "d93f0b"
LABEL_CREATE_PATH_TEMPLATE = "repos/{repository}/labels"
LABEL_DESCRIPTION = "A correction the user gave an agent, waiting for a control"
LABEL_FIELD_TEMPLATE = "labels[]={value}"
LABEL_PATH_TEMPLATE = "repos/{repository}/labels/{label}"
LEDGER_FILE_NAME = "correction-capture-filed.json"
LEDGER_KEY_TEMPLATE = "{repository} {dedupe_key}"
LINE_SEPARATOR = "\n"
LIST_FALLBACK_LINE_TEMPLATE = "Listing the correction inbox {inbox}: {reasons}\n"
LIST_LINE_TEMPLATE = "#{number} {title} {url}\n"
MANAGED_ROOT_ENV_VAR = "CLAUDE_CONFIG_DIR"
NO_OPEN_CORRECTIONS_MESSAGE = "No open corrections.\n"
NO_TARGET_MESSAGE_TEMPLATE = (
    "No repository can take this correction: {reasons}. A fallback inbox is "
    '{{"repository": "<owner>/<name>"}} in {config_path}. Nothing was filed. '
    "Print the brief in your reply and say why.\n"
)
PREAMBLE_SEPARATOR = "\n\n"
OCCURRENCE_MARKER_TEMPLATE = "<!-- correction-occurrence: {key} -->"
ORIGIN_REMOTE_NAME = "origin"
POST_LINT_ACTION_COMMENT = "issue-comment"
POST_LINT_ACTION_CREATE = "issue-create"
POST_LINT_BODY_FILE_NAME = "correction-body.md"
POST_LINT_MISSING_MESSAGE_TEMPLATE = (
    "The durable post lint is missing at {path}. Install claude-dev-env, then "
    "run again. Nothing was filed.\n"
)
POST_LINT_REFUSED_MESSAGE_TEMPLATE = (
    "{findings}The durable post lint refused the issue for {repository}. Reword "
    "the brief and run again. Nothing was filed.\n"
)
REASON_ISSUES_OFF_TEMPLATE = "{repository} has issues turned off"
REASON_NO_ORIGIN_TEMPLATE = "found no origin remote for {checkout}"
REASON_NOT_GITHUB_TEMPLATE = "origin {origin_url} is not a GitHub repository"
REASON_SEPARATOR = "; "
REASON_UNREACHABLE_TEMPLATE = "cannot reach {repository}: {detail}"
REDACTION_PLACEHOLDER = "[redacted]"
REPEAT_COMMENT_TEMPLATE = (
    "## Repeat\n\n"
    "The user gave this correction again, so the control that lands for it "
    "belongs one layer above the one that let it through.\n\n"
    "Source: {source}\n\n"
    "{quoted_text}\n\n"
    "{occurrence_marker}\n"
)
REPEAT_LINE_TEMPLATE = "Repeat of {earlier_url}, which is closed.\n"
REPEAT_MARKED_MESSAGE_TEMPLATE = "Repeat marked on {issue_url}: {comment_url}{note}\n"
REPOSITORY_PROBE_JQ_FILTER = "{private, has_issues}"
REPOSITORY_PROBE_PATH_TEMPLATE = "repos/{repository}"
STATE_ALL = "all"
STATE_OPEN = "open"
SUCCESS_EXIT_CODE = 0
TITLE_FIELD_TEMPLATE = "title={value}"
UTF8_ENCODING = "utf-8"
WORD_SEPARATOR = " "
