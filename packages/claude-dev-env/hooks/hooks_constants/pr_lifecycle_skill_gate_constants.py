"""Constants for the pull request lifecycle skill gate."""

HOOK_EVENT_NAME = "PreToolUse"
HOOK_SPECIFIC_OUTPUT_KEY = "hookSpecificOutput"
PERMISSION_DECISION_KEY = "permissionDecision"
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
OPTION_AND_VALUE_WORD_COUNT = 2
GIT_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})
GH_OPTIONS_WITH_VALUE = frozenset({"-R", "--repo", "--hostname", "--config", "-H", "--header", "-X", "--method", "-F", "--field", "-f", "--raw-field", "--input", "--jq", "-q", "--template", "-t", "--cache"})
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
