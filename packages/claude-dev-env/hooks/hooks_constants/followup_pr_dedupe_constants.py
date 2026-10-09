"""Constants for the one-follow-up-pull-request-per-parent check."""

FOLLOWUP_PARENT_PATTERN = r"follow[- ]?up to #(\d+)(?!\d)"
GITHUB_API_ROOT = "https://api.github.com"
OPEN_PULL_REQUESTS_PATH_TEMPLATE = "/repos/{owner}/{repo}/pulls?state=open&per_page=100"
READ_TIMEOUT_SECONDS = 4
ALL_GH_CREATE_WORDS = ["pr", "create"]
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
ALL_TITLE_OPTIONS = frozenset({"-t", "--title"})
WORKFLOW_DISPATCH_TOOL_SUFFIX = "__actions_run_trigger"
RUN_WORKFLOW_METHOD = "run_workflow"
ALL_PULL_REQUEST_DISPATCH_INPUT_KEYS = ("head", "title")
