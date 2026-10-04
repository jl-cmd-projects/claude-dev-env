"""Constants for the one-follow-up-pull-request-per-parent CI check."""

FOLLOWUP_PARENT_PATTERN = r"follow[- ]?up to #(\d+)(?!\d)"
RULE_START_TIMESTAMP = "2026-10-04T12:00:00Z"
OPEN_PULL_REQUESTS_ENDPOINT_TEMPLATE = "{api_root}/repos/{slug}/pulls?state=open&per_page=100"
PASS_EXIT_CODE = 0
DUPLICATE_EXIT_CODE = 1
ERROR_EXIT_CODE = 2
PASS_MESSAGE = "No earlier open follow-up pull request names this parent."
DUPLICATE_FOLLOWUP_MESSAGE_TEMPLATE = (
    "Pull request #{open_number} already holds the follow-up findings for parent #{parent_number}"
    " ({open_url}). Add this finding to the open follow-up pull request #{open_number}."
    " One combined follow-up pull request per parent pull request."
)
