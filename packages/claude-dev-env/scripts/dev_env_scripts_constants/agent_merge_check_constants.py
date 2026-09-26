"""Named constants for agent_merge_check, the agent merge check."""

from __future__ import annotations

GITHUB_API_ROOT = "https://api.github.com"
GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
PULL_REQUEST_ENDPOINT_TEMPLATE = "{api_root}/repos/{slug}/pulls/{number}"
REVIEW_THREADS_ENDPOINT_TEMPLATE = (
    "{api_root}/repos/{slug}/pulls/{number}/ccr/review_threads"
)
ACCEPT_HEADER = "Accept"
GITHUB_ACCEPT_TYPE = "application/vnd.github+json"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
CONTENT_TYPE_HEADER = "Content-Type"
JSON_CONTENT_TYPE = "application/json"
UTF8_ENCODING = "utf-8"
REQUEST_TIMEOUT_SECONDS = 30

ALL_TOKEN_ENVIRONMENT_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN")

DRAFT_KEY = "draft"
MERGEABLE_STATE_KEY = "mergeable_state"
NUMBER_KEY = "number"
TITLE_KEY = "title"
HEAD_KEY = "head"
BASE_KEY = "base"
REF_KEY = "ref"
SHA_KEY = "sha"

BRANCH_RULES_ENDPOINT_TEMPLATE = "{api_root}/repos/{slug}/rules/branches/{branch}"
CHECK_RUNS_ENDPOINT_TEMPLATE = (
    "{api_root}/repos/{slug}/commits/{sha}/check-runs?{query}"
)
COMBINED_STATUS_ENDPOINT_TEMPLATE = (
    "{api_root}/repos/{slug}/commits/{sha}/status?{query}"
)
COMPARE_ENDPOINT_TEMPLATE = "{api_root}/repos/{slug}/compare/{base}...{head}"
CHECK_NAME_PARAMETER = "check_name"
PER_PAGE_PARAMETER = "per_page"
CHECK_PAGE_SIZE = 100

RULE_TYPE_KEY = "type"
RULE_PARAMETERS_KEY = "parameters"
REQUIRED_STATUS_CHECKS_RULE_TYPE = "required_status_checks"
MERGE_QUEUE_RULE_TYPE = "merge_queue"
REQUIRED_STATUS_CHECKS_KEY = "required_status_checks"
CONTEXT_KEY = "context"
INTEGRATION_ID_KEY = "integration_id"
CHECK_RUNS_KEY = "check_runs"
CHECK_RUN_NAME_KEY = "name"
CHECK_RUN_ID_KEY = "id"
CHECK_RUN_APP_KEY = "app"
CHECK_RUN_APP_ID_KEY = "id"
CHECK_RUN_STATUS_KEY = "status"
CHECK_RUN_CONCLUSION_KEY = "conclusion"
CHECK_RUN_COMPLETED_STATUS = "completed"
ALL_PASSING_CHECK_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
STATUSES_KEY = "statuses"
STATUS_STATE_KEY = "state"
SUCCESS_STATUS_STATE = "success"
PENDING_STATUS_STATE = "pending"
BEHIND_BY_KEY = "behind_by"

MERGEABLE_STATE_CLEAN = "clean"
MERGEABLE_STATE_BEHIND = "behind"
MERGEABLE_STATE_DIRTY = "dirty"
MERGEABLE_STATE_BLOCKED = "blocked"
MERGEABLE_STATE_UNSTABLE = "unstable"
MERGEABLE_STATE_UNKNOWN = "unknown"
SETTLE_ATTEMPT_COUNT = 5
SETTLE_WAIT_SECONDS = 3

DRAFT_HOLD_REASON = (
    "The pull request is a draft, so it carries no verdict to merge on. "
    "Mark it ready once its checks pass."
)
BEHIND_HOLD_REASON = (
    "The head is behind the base branch and the branch rule requires an "
    "up-to-date head. Merge the base branch into this one and push."
)
DIRTY_HOLD_REASON = (
    "The head conflicts with the base branch. Merge the base branch into "
    "this one, resolve the conflict, and push."
)
BLOCKED_HOLD_REASON = (
    "A required status check is not passing on this head. Read the failing "
    "check, fix it, and push."
)
UNSTABLE_HOLD_REASON = (
    "A check on this head is failing or still running. Wait for it, and fix "
    "it when it comes back red."
)
ALL_HOLD_REASONS_BY_STATE = {
    MERGEABLE_STATE_BEHIND: BEHIND_HOLD_REASON,
    MERGEABLE_STATE_DIRTY: DIRTY_HOLD_REASON,
    MERGEABLE_STATE_BLOCKED: BLOCKED_HOLD_REASON,
    MERGEABLE_STATE_UNSTABLE: UNSTABLE_HOLD_REASON,
}
FAILING_REQUIRED_CHECKS_HOLD_TEMPLATE = (
    "A required check is not passing on this head: {checks}. Read the "
    "failing check, fix it, and push."
)
REQUIRED_CHECK_STATE_TEMPLATE = "{context} ({state})"
REQUIRED_CHECK_SEPARATOR = ", "
MISSING_CHECK_STATE = "missing"
PENDING_CHECK_STATE = "pending"
BEHIND_MERGE_QUEUE_HOLD_TEMPLATE = (
    "Every required check passes, but the head is {count} commit(s) behind "
    "the base branch and the merge queue will not take it. Merge the base "
    "branch into this one and push."
)
UNKNOWN_STATE_HOLD_TEMPLATE = (
    "GitHub reports the merge state as {state}, which this check does not "
    "treat as ready. Read the pull request page."
)
UNRESOLVED_THREADS_HOLD_TEMPLATE = (
    "{count} review thread(s) are open. Answer each one and resolve it."
)
MERGE_QUEUE_EJECTION_HOLD_TEMPLATE = (
    "The merge queue ejected this head for failed checks, and no commit has "
    "landed since. Read the merge_group run for the "
    "gh-readonly-queue/{base}/pr-{number}-<sha> branch, fix the failure, and "
    "push before you enqueue it again."
)
FAILED_CHECKS_REMOVAL_REASON = "failed_checks"

MERGE_VERDICT_LABEL = "MERGE"
HOLD_VERDICT_LABEL = "HOLD"
VERDICT_LINE_TEMPLATE = "{label} {slug}#{number} {sha} :: {detail}"
SHORT_SHA_LENGTH = 7
READY_DETAIL = "green, no open review thread, ready for the agent to merge"

MERGE_EXIT_CODE = 0
HOLD_EXIT_CODE = 1
ERROR_EXIT_CODE = 2

NO_SIGN_IN_MESSAGE = "No GitHub token in the environment. Set GH_TOKEN or GITHUB_TOKEN."
SLUG_SEPARATOR = "/"
SLUG_ARGUMENT_HELP = "Repository as owner/name, such as jl-cmd/claude-dev-env."
NUMBER_ARGUMENT_HELP = "Pull request number."
COMMAND_DESCRIPTION = (
    "Report whether a pull request is ready for the agent that drives it to merge it."
)

REVIEW_THREAD_PAGE_SIZE = 100
UNRESOLVED_THREAD_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $pageSize: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: $pageSize) {
        nodes { isResolved isOutdated }
      }
    }
  }
}
"""
MERGE_QUEUE_REMOVAL_PAGE_SIZE = 100
MERGE_QUEUE_REMOVAL_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $pageSize: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      commits(last: 1) { nodes { commit { committedDate } } }
      timelineItems(last: $pageSize, itemTypes: [REMOVED_FROM_MERGE_QUEUE_EVENT]) {
        nodes { ... on RemovedFromMergeQueueEvent { createdAt reason } }
      }
    }
  }
}
"""
QUERY_KEY = "query"
VARIABLES_KEY = "variables"
OWNER_VARIABLE = "owner"
NAME_VARIABLE = "name"
NUMBER_VARIABLE = "number"
PAGE_SIZE_VARIABLE = "pageSize"
DATA_KEY = "data"
REPOSITORY_KEY = "repository"
PULL_REQUEST_KEY = "pullRequest"
REVIEW_THREADS_KEY = "reviewThreads"
NODES_KEY = "nodes"
ALL_THREAD_NODE_KEYS = (
    DATA_KEY,
    REPOSITORY_KEY,
    PULL_REQUEST_KEY,
    REVIEW_THREADS_KEY,
    NODES_KEY,
)
COMMITS_KEY = "commits"
COMMIT_KEY = "commit"
COMMITTED_DATE_KEY = "committedDate"
TIMELINE_ITEMS_KEY = "timelineItems"
CREATED_AT_KEY = "createdAt"
REMOVAL_REASON_KEY = "reason"
ALL_MERGE_QUEUE_REMOVAL_NODE_KEYS = (
    DATA_KEY,
    REPOSITORY_KEY,
    PULL_REQUEST_KEY,
    TIMELINE_ITEMS_KEY,
    NODES_KEY,
)
ALL_HEAD_COMMIT_NODE_KEYS = (
    DATA_KEY,
    REPOSITORY_KEY,
    PULL_REQUEST_KEY,
    COMMITS_KEY,
    NODES_KEY,
)
ALL_RESOLVED_KEYS = ("isResolved", "is_resolved", "resolved")
ALL_OUTDATED_KEYS = ("isOutdated", "is_outdated", "outdated")
