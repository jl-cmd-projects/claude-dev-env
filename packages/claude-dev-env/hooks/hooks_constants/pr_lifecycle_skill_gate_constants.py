"""Constants for the pull request lifecycle skill gate."""

import re

HOOK_EVENT_NAME = "PreToolUse"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
DENY_DECISION = "deny"
DENY_REASON = (
    "Invoke the pr-lifecycle skill with the Skill tool, then run the same command again."
)
SKILL_NAME = "pr-lifecycle"
ALL_SLASH_COMMAND_MARKERS = ("<command-name>/pr-lifecycle</command-name>",)
SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})
ALL_GITHUB_MCP_TOOL_SUFFIXES = (
    "__create_pull_request",
    "__merge_pull_request",
    "__enable_pr_auto_merge",
    "__update_pull_request",
)
ALL_TRANSCRIPT_PATH_FIELDS = ("transcript_path", "agent_transcript_path")
SESSION_TRANSCRIPT_PATH_FIELD = "transcript_path"
AGENT_ID_FIELD = "agent_id"
AGENT_ID_PATTERN = r"[A-Za-z0-9_-]+"
SUBAGENT_TRANSCRIPT_DIRECTORY_NAME = "subagents"
SUBAGENT_TRANSCRIPT_FILE_TEMPLATE = "agent-{agent_id}.jsonl"
COMMAND_SEPARATORS = ";|&\n()`"
COMMAND_WHITESPACE = " \t\r"
NO_COMMENT_CHARACTERS = ""
REMOVED_TEXT = ""
SEGMENT_BREAK = "\0"
SEPARATOR_PIECE = "separator"
COMMENT_PIECE = "comment"
LINE_CONTINUATION_PIECE = "continuation"
UNCLOSED_QUOTE_PIECE = "unclosed"
COMMAND_PIECE_PATTERN = re.compile(
    r"'[^']*'"
    r'|"(?:\\.|[^"\\])*"'
    rf"|(?P<{LINE_CONTINUATION_PIECE}>\\\n)"
    rf"|\\.[^{re.escape(COMMAND_WHITESPACE + COMMAND_SEPARATORS)}'\"\\]*"
    rf"|(?P<{COMMENT_PIECE}>(?<![^{re.escape(COMMAND_WHITESPACE + COMMAND_SEPARATORS)}])(?<!\\\n)#[^\n]*)"
    rf"|(?P<{SEPARATOR_PIECE}>[{re.escape(COMMAND_SEPARATORS)}])"
    rf"|(?P<{UNCLOSED_QUOTE_PIECE}>['\"])"
    r"|.",
    re.DOTALL,
)
OPTION_AND_VALUE_WORD_COUNT = 2
GIT_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})
GIT_ACTIONS = frozenset({"commit", "push"})
GH_PULL_REQUEST_COMMAND = "pr"
GH_API_COMMAND = "api"
MERGE_PATH_SUFFIX = "/merge"
ALL_API_ACTION_NAMES = ("auto-merge", "enablePullRequestAutoMerge")
ALL_COMMAND_PREFIX_WORDS = frozenset({"env", "sudo", "command", "exec", "nohup", "time"})
ALL_PREFIX_OPTIONS_WITH_VALUE = frozenset({"-u", "--unset", "-C", "--chdir", "-g", "--group", "--user"})
ENVIRONMENT_ASSIGNMENT_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*="
ALL_SHELL_WRAPPER_EXECUTABLES = frozenset({"bash", "sh", "zsh", "dash", "pwsh", "pwsh.exe", "powershell", "powershell.exe"})
ALL_PYTHON_EXECUTABLES = frozenset({"python", "python3", "python.exe", "python3.exe", "py", "py.exe"})
PULL_REQUEST_SCRIPT_NAME = "pull_request.py"
PATH_SEPARATOR_PATTERN = r"[\\/]"
PYTHON_OPTIONS_WITH_VALUE = frozenset({"-X", "-W"})
ALL_BUILD_EVAL_SKILL_NAMES = ("claude-api",)
BUILD_EVAL_ARGUMENT_WORD = "build-eval"
BUILD_EVAL_COMMAND_MARKER = "<command-name>/claude-api</command-name>"
