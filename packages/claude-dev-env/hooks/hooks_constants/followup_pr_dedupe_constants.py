"""Constants for the one-follow-up-pull-request-per-parent check."""

FOLLOWUP_PARENT_PATTERN = r"follow[- ]?up to #(\d+)(?!\d)"
GITHUB_API_ROOT = "https://api.github.com"
OPEN_PULL_REQUESTS_PATH_TEMPLATE = "/repos/{owner}/{repo}/pulls?state=open&per_page=100"
READ_TIMEOUT_SECONDS = 4
ALL_BODY_OPTIONS = frozenset({"-b", "--body"})
ALL_BODY_FILE_OPTIONS = frozenset({"-F", "--body-file"})
ALL_REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
STANDARD_INPUT_PATH = "-"
CREATE_PULL_REQUEST_TOOL_SUFFIX = "__create_pull_request"
GITHUB_REMOTE_PATTERN = r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$"
ALL_GIT_REMOTE_COMMAND_WORDS = ("git", "remote", "get-url", "origin")
DUPLICATE_FOLLOWUP_REASON_TEMPLATE = (
    "Pull request #{open_number} already holds the follow-up findings for parent #{parent_number}"
    " ({open_url}). Add this finding to the open follow-up pull request #{open_number}."
    " One combined follow-up pull request per parent pull request."
)
PREFIX_ORIGIN_FOLLOWUP_SENTENCE = (
    " This create names its repository only with a `GH_REPO=` prefix, and a wrapper such as "
    "`env -u GH_REPO` can drop that prefix before gh runs, so the gate also reads the origin "
    "repository. Name the repository with `--repo owner/name` on the create instead."
)
UNANSWERED_FOLLOWUP_REASON_TEMPLATE = (
    "The gate could not read the open pull requests of {owner}/{repo}: the read timed out"
    " or GitHub answered with a server error. So it cannot tell"
    " whether parent #{parent_number} already has an open follow-up pull request."
    " Run the create again."
)
UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE = (
    "The gate could not read the origin remote, so it cannot tell which repository to check"
    " for an open follow-up pull request to parent #{parent_number}."
    " Name the repository with --repo and run the create again."
)
GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE = (
    "The command sets GH_REPO, so the gate cannot tell which repository a create with no"
    " --repo opens in, or which one to check for an open follow-up pull request to parent"
    " #{parent_number}. Name the repository with --repo and run the create again."
)
ALL_TITLE_OPTIONS = frozenset({"-t", "--title"})
GH_PROGRAM_NAME = "gh"
ALL_GH_ACTION_WORDS_BY_ALIAS = {"new": "create"}
GH_REPOSITORY_ENVIRONMENT_PREFIX = "GH_REPO="
GH_REPOSITORY_APPEND_PREFIX = "GH_REPO+="
APPEND_ASSIGNMENT_MARK = "+"
GH_REPOSITORY_ENVIRONMENT_NAME = "GH_REPO"
ALL_VARIABLE_SETTING_PROGRAM_NAMES = frozenset({"export", "declare", "typeset", "local", "readonly"})
ASSIGNMENT_SEPARATOR = "="
REPOSITORY_OPTION = "--repo"
OPTION_PREFIX = "-"
LONG_OPTION_PREFIX = "--"
STANDARD_INPUT_SCRIPT = "-"
SHORT_OPTION_LENGTH = 2
OPTION_AND_VALUE_WIDTH = 2
WINDOWS_EXECUTABLE_SUFFIX = ".exe"
PYTHON_PROGRAM_NAME_PATTERN = r"python(?:\d+(?:\.\d+)*)?w?|pyw?"
ALL_PYTHON_OPTIONS_WITH_VALUE = frozenset({"-X", "-W", "--check-hash-based-pycs"})
ALL_PYTHON_NON_SCRIPT_OPTIONS = frozenset({"-c", "-m"})
WORKFLOW_DISPATCH_TOOL_SUFFIX = "__actions_run_trigger"
RUN_WORKFLOW_METHOD = "run_workflow"
ALL_PULL_REQUEST_DISPATCH_INPUT_KEYS = ("head", "title")
