"""Constants for the Stop hook that reviews each turn's changes in a fresh context."""

from __future__ import annotations

__all__ = [
    "REPOSITORIES_ENVIRONMENT_VARIABLE",
    "REPOSITORY_SEPARATOR",
    "PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE",
    "REVIEW_CHILD_ENVIRONMENT_VARIABLE",
    "REVIEW_CHILD_MARKER",
    "ALL_PARENT_SESSION_VARIABLES",
    "PROMPT_EVENT_NAME",
    "STOP_EVENT_NAME",
    "HOOK_EVENT_NAME_KEY",
    "SESSION_ID_KEY",
    "GIT_DIRECTORY_NAME",
    "GIT_COMMAND_TIMEOUT_SECONDS",
    "GIT_INDEX_FILE_ENVIRONMENT_VARIABLE",
    "TEMPORARY_INDEX_FILE_NAME",
    "ALL_INDEX_PATH_ARGUMENTS",
    "ALL_CHANGED_PATH_ARGUMENTS",
    "CHANGED_PATH_SEPARATOR",
    "GIT_OUTPUT_ENCODING",
    "GIT_OUTPUT_ERROR_HANDLING",
    "SNAPSHOT_COMMIT_MESSAGE",
    "ALL_SNAPSHOT_IDENTITY_VARIABLES",
    "MAXIMUM_TURN_FILES",
    "MAXIMUM_BLOCKS_IN_A_ROW",
    "REVIEW_EFFORT",
    "REVIEW_MODEL_ALIAS",
    "REVIEW_TIMEOUT_SECONDS",
    "STOP_RUN_BUDGET_SECONDS",
    "PROMPT_RUN_BUDGET_SECONDS",
    "MINIMUM_REVIEW_SECONDS",
    "REVIEW_PROMPT_TEMPLATE",
    "ALL_REVIEW_ALLOWED_TOOLS",
    "ALL_REVIEW_DISALLOWED_TOOLS",
    "REVIEW_EXECUTABLE_NAME",
    "REVIEW_SETTING_SOURCES_TEXT",
    "REVIEW_TOOLS_TEXT",
    "REVIEW_SETTINGS_TEXT",
    "REVIEW_RESULT_KEY",
    "FINDING_LINE_PATTERN_TEMPLATE",
    "JSON_FINDING_FILE_KEY",
    "JSON_FINDING_LINE_KEY",
    "JSON_FINDING_SUMMARY_KEY",
    "JSON_FINDING_LINE_TEMPLATE",
    "JSON_ARRAY_START",
    "NO_FINDINGS_MARKER",
    "STATE_FILE_TEMPLATE",
    "STATE_BASELINES_KEY",
    "BASELINE_COMMIT_PATTERN",
    "STATE_BLOCKS_KEY",
    "STATE_TEMPORARY_PREFIX",
    "STATE_TEXT_ENCODING",
    "REPOSITORY_FINDINGS_TEMPLATE",
    "FINDING_LINE_SEPARATOR",
    "REPOSITORY_FINDINGS_SEPARATOR",
    "BLOCK_REASON_TEMPLATE",
    "TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE",
    "REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE",
    "STATE_SAVE_FAILURE_DIAGNOSTIC_TEMPLATE",
    "STATE_TURN_OPEN_KEY",
    "STATE_LAST_WAKE_KEY",
    "STATE_OPEN_TURN_PROMPT_KEY",
    "RACING_STOP_WINDOW_SECONDS",
    "WAKE_PROMPT_WINDOW_SECONDS",
    "PROMPT_KEY",
    "MACHINE_PROMPT_PREFIX",
    "STATE_LOCK_FILE_TEMPLATE",
    "STATE_LOCK_FILE_MODE",
    "STATE_LOCK_WAIT_SECONDS",
    "STATE_LOCK_OUTCOME_WAIT_SECONDS",
    "STATE_LOCK_RETRY_SECONDS",
    "STATE_LOCK_BYTE_COUNT",
    "STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE",
    "STOP_HOOK_ACTIVE_KEY",
    "RUN_DIAGNOSTIC_TEMPLATE",
    "ALL_LOG_PATH_PARTS",
    "LOG_LINE_TEMPLATE",
    "LOG_TEXT_ENCODING",
]

REPOSITORIES_ENVIRONMENT_VARIABLE = "CLAUDE_TURN_REVIEW_REPOSITORIES"
REPOSITORY_SEPARATOR = ","
PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE = "CLAUDE_PROJECT_DIR"
REVIEW_CHILD_ENVIRONMENT_VARIABLE = "CLAUDE_TURN_REVIEW_CHILD"
REVIEW_CHILD_MARKER = "1"
ALL_PARENT_SESSION_VARIABLES = frozenset(
    {
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_REMOTE_SESSION_ID",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
        "CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2",
        "CLAUDE_CODE_TEE_SDK_STDOUT",
    }
)
PROMPT_EVENT_NAME = "UserPromptSubmit"
STOP_EVENT_NAME = "Stop"
HOOK_EVENT_NAME_KEY = "hook_event_name"
SESSION_ID_KEY = "session_id"
GIT_DIRECTORY_NAME = ".git"
GIT_COMMAND_TIMEOUT_SECONDS = 30
GIT_INDEX_FILE_ENVIRONMENT_VARIABLE = "GIT_INDEX_FILE"
TEMPORARY_INDEX_FILE_NAME = "index"
ALL_INDEX_PATH_ARGUMENTS = ("rev-parse", "--git-path", "index")
ALL_CHANGED_PATH_ARGUMENTS = ("diff", "--name-only", "-z")
CHANGED_PATH_SEPARATOR = "\0"
GIT_OUTPUT_ENCODING = "utf-8"
GIT_OUTPUT_ERROR_HANDLING = "surrogateescape"
SNAPSHOT_COMMIT_MESSAGE = "turn review snapshot"
ALL_SNAPSHOT_IDENTITY_VARIABLES = {
    "GIT_AUTHOR_NAME": "turn review",
    "GIT_AUTHOR_EMAIL": "turn-review",
    "GIT_COMMITTER_NAME": "turn review",
    "GIT_COMMITTER_EMAIL": "turn-review",
}
MAXIMUM_TURN_FILES = 30
MAXIMUM_BLOCKS_IN_A_ROW = 3
REVIEW_EFFORT = "low"
REVIEW_MODEL_ALIAS = "opus"
REVIEW_TIMEOUT_SECONDS = 240
STOP_RUN_BUDGET_SECONDS = 280
PROMPT_RUN_BUDGET_SECONDS = 25
MINIMUM_REVIEW_SECONDS = 1
REVIEW_PROMPT_TEMPLATE = "/code-review {effort} {base_commit}..{turn_commit}"
ALL_REVIEW_ALLOWED_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash(git diff:*)",
    "Bash(git show:*)",
    "Bash(git log:*)",
)
ALL_REVIEW_DISALLOWED_TOOLS = (
    "Bash(git * -c *)",
    "Bash(git *--config-env*)",
    "Bash(git *--output*)",
    "Bash(git *--ext-diff*)",
    "Bash(git *--textconv*)",
    "Bash(git *--git-dir*)",
    "Bash(git *--work-tree*)",
    "Bash(git *--exec-path*)",
)
REVIEW_EXECUTABLE_NAME = "claude"
REVIEW_SETTING_SOURCES_TEXT = ""
REVIEW_TOOLS_TEXT = "Read,Grep,Glob,Bash"
REVIEW_SETTINGS_TEXT = '{"disableAllHooks": true}'
REVIEW_RESULT_KEY = "result"
FINDING_LINE_PATTERN_TEMPLATE = r"^\s*(?:[-*+]|\d+[.)])?\s*[`*_]*{path}:\d+"
JSON_FINDING_FILE_KEY = "file"
JSON_FINDING_LINE_KEY = "line"
JSON_FINDING_SUMMARY_KEY = "summary"
JSON_FINDING_LINE_TEMPLATE = "{path}:{line} {summary}"
JSON_ARRAY_START = "["
NO_FINDINGS_MARKER = "(none)"
STATE_FILE_TEMPLATE = "turn-review-{session_id}.json"
STATE_BASELINES_KEY = "baselines"
BASELINE_COMMIT_PATTERN = r"[0-9a-f]{40}|[0-9a-f]{64}"
STATE_BLOCKS_KEY = "blocks_in_a_row"
STATE_TEMPORARY_PREFIX = ".turn-review-"
STATE_TEXT_ENCODING = "utf-8"
REPOSITORY_FINDINGS_TEMPLATE = "{repository}:\n{findings}"
FINDING_LINE_SEPARATOR = "\n"
REPOSITORY_FINDINGS_SEPARATOR = "\n\n"
BLOCK_REASON_TEMPLATE = (
    "A fresh-context review of the changes you made since the last review found these "
    "problems. Fix each one. Code the user pasted or described is not a "
    "request for the problem it causes. Keep a finding's behavior only when the user's own "
    "words ask for that behavior, and quote those words in your reply. When a finding is "
    "wrong, say in your reply why:\n\n"
    "{all_findings}"
)
TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE = (
    "[turn_review_gate] {repository}: {count} files changed this turn, over the "
    "{limit}-file limit, so no review ran\n"
)
REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE = (
    "[turn_review_gate] review of {repository} did not finish: {reason}\n"
)
STATE_SAVE_FAILURE_DIAGNOSTIC_TEMPLATE = (
    "[turn_review_gate] the review state was not saved: {detail}\n"
)
STATE_TURN_OPEN_KEY = "turn_open"
STATE_LAST_WAKE_KEY = "last_wake_at"
STATE_OPEN_TURN_PROMPT_KEY = "open_turn_prompt_at"
RACING_STOP_WINDOW_SECONDS = 10
WAKE_PROMPT_WINDOW_SECONDS = 10
PROMPT_KEY = "prompt"
MACHINE_PROMPT_PREFIX = "<task-notification"
STATE_LOCK_FILE_TEMPLATE = "turn-review-{session_id}.lock"
STATE_LOCK_FILE_MODE = 0o600
STATE_LOCK_WAIT_SECONDS = 3
STATE_LOCK_OUTCOME_WAIT_SECONDS = 35
STATE_LOCK_RETRY_SECONDS = 0.05
STATE_LOCK_BYTE_COUNT = 1
STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE = (
    "[turn_review_gate] {event} left the review state alone: another run held its lock\n"
)
STOP_HOOK_ACTIVE_KEY = "stop_hook_active"
RUN_DIAGNOSTIC_TEMPLATE = "[turn_review_gate] {event} stop_hook_active={stop_hook_active}\n"
ALL_LOG_PATH_PARTS = (".claude", "logs", "turn-review.log")
LOG_LINE_TEMPLATE = "{timestamp} {text}"
LOG_TEXT_ENCODING = "utf-8"
