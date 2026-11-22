"""Named constants for merge_review_gate, the clean-review open and merge gate."""

from __future__ import annotations

import os
import re

HOOK_EVENT_NAME = "PreToolUse"
GATE_NAME = "merge review"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"

MERGE_TOOL_SUFFIX = "__merge_pull_request"
AUTO_MERGE_TOOL_SUFFIX = "__enable_pr_auto_merge"
CREATE_TOOL_SUFFIX = "__create_pull_request"
ALL_SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

OWNER_FIELD = "owner"
REPO_FIELD = "repo"
NUMBER_FIELD = "pullNumber"
EXPECTED_HEAD_FIELD = "expectedHeadSha"
HEAD_BRANCH_FIELD = "head"
BASE_BRANCH_FIELD = "base"
CWD_FIELD = "cwd"

ALL_HEAD_OPTIONS = frozenset({"-H", "--head"})
ALL_REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
LONG_REPOSITORY_OPTION = "--repo"
REPOSITORY_SHORT_LETTER = "R"
HEAD_SHORT_LETTER = "H"
LONG_BASE_OPTION = "--base"
BASE_SHORT_LETTER = "B"
SHORT_OPTION_PREFIX = "-"
OPTION_AND_VALUE_WIDTH = 2
GH_PROGRAM_NAME = "gh"
ALL_VALUELESS_LONG_CREATE_OPTIONS = frozenset(
    {
        "--draft",
        "--dry-run",
        "--editor",
        "--fill",
        "--fill-first",
        "--fill-verbose",
        "--help",
        "--no-maintainer-edit",
        "--web",
    }
)
ALL_VALUELESS_SHORT_CREATE_LETTERS = frozenset({"d", "e", "f", "h", "w"})
ALL_CHANGE_FOLDER_PROGRAMS = frozenset({"cd", "chdir", "set-location", "sl"})
ALL_HOME_DEFAULT_PROGRAMS = frozenset({"cd", "chdir"})
ALL_PUSH_FOLDER_PROGRAMS = frozenset({"pushd", "push-location"})
ALL_POP_FOLDER_PROGRAMS = frozenset({"popd", "pop-location"})
ALL_FOLDER_CHANGE_WORDS = (
    ALL_CHANGE_FOLDER_PROGRAMS | ALL_PUSH_FOLDER_PROGRAMS | ALL_POP_FOLDER_PROGRAMS
)
ALL_SETTLED_FOLDER_PROGRAMS = frozenset({"cd", "pushd"})
ALL_SETTLED_SUBSTITUTION_PROGRAMS = frozenset({"cat", "echo", "printf"})
ALL_SETTLED_BEFORE_PROGRAMS = (
    ALL_SETTLED_FOLDER_PROGRAMS | ALL_SETTLED_SUBSTITUTION_PROGRAMS | frozenset({"head", "tail"})
)
ALL_SETTLED_PIPE_READER_PROGRAMS = frozenset({"cat", "head", "tail", "tee", "grep"})
ALL_OUTPUT_REDIRECT_OPERATORS = frozenset({">", ">>", ">|", "&>", "&>>", ">&", "<>"})
ALL_REDIRECT_OPERATORS = ALL_OUTPUT_REDIRECT_OPERATORS | frozenset({"<", "<&", "<<<"})
FILE_DESCRIPTOR_COPY_OPERATOR = ">&"
FILE_DESCRIPTOR_COPY_TARGET_PATTERN = re.compile(r"\d+-?|-")
NULL_DEVICE_PATH = "/dev/null"
GIT_FOLDER_NAME = ".git"
HEREDOC_OPERATOR_TOKEN = "<<"
FUNCTION_DEFINITION_TOKEN = "()"
PRINTF_PROGRAM_NAME = "printf"
PRINTF_VARIABLE_OPTION_PREFIX = "-v"
TEE_PROGRAM_NAME = "tee"
ALL_UNSETTLED_WRITE_TARGET_CHARACTERS = frozenset("$`*?[{~")
PROCESS_SUBSTITUTION_PATTERN = re.compile(r"[<>]\(")
SUBSCRIPT_EXPANSION_PATTERN = re.compile(r"\$\{[!#]?\w+\[")
UNSETTLED_EXPANSION_PATTERN = re.compile(r"\$\[|\$\(\(|\$\{(?![A-Za-z0-9_]+(?:\}|:?[-+?]))")
FOLDER_PATH_SEPARATOR_PATTERN = re.compile(r"[/\\]")
ALL_IGNORED_FOLDER_NAME_END_CHARACTERS = ". "
FOLDER_STACK_ROTATION_PREFIX = "+"
HOME_FOLDER_PREFIX = "~/"
UNSETTLED_PREFIX_NAME_PATTERN = re.compile(
    r"(?i:(?:GIT|LD|DYLD|XDG|UV)_\w*|PYTHON\w*|HOME|PATH)|(?!GH_REPO\Z)(?i:GH_\w*)"
)
ALL_SETTLED_CREATE_LAUNCHER_WORDS = ("uv", "run")
ASSIGNMENT_SEPARATOR = "="
APPEND_ASSIGNMENT_MARK = "+"
ALL_PATH_PARAMETER_NAMES = frozenset({"-path", "-literalpath"})
ALL_UNFOLLOWED_FOLDER_CHARACTERS = frozenset("$`*?[{%")
PREVIOUS_FOLDER_ARGUMENT = "-"
HOME_FOLDER = "~"
OPTION_PREFIX = "-"
SUBSHELL_OPEN_OPERATOR = "("
SUBSHELL_CLOSE_TOKEN = ")"
ALL_PIPE_OPERATORS = frozenset({"|", "|&"})
ALL_BACKGROUND_OPERATORS = frozenset({"&"})
BRACE_OPEN_OPERATOR = "{"
BRACE_CLOSE_TOKEN = "}"
ALL_COMPOUND_OPEN_WORDS = frozenset({"if", "while", "until", "for", "case", "select"})
ALL_COMPOUND_CLOSE_WORDS = frozenset({"fi", "done", "esac"})
ALL_COMPOUND_BODY_WORDS = frozenset({"then", "elif", "else", "do"})
ALL_COMMAND_PREFIX_WORDS = frozenset({"builtin", "command"})
SEGMENT_TOKEN_JOIN = " "
IS_POSIX_TOKENIZATION = True
ALL_UNBALANCED_TOKENIZATION_MODES = (True, False)
ANSI_C_QUOTE_OPENER = "$'"
GROUP_OPEN_CHARACTER = "("
GROUP_CLOSE_CHARACTER = ")"
COMMENT_START_CHARACTER = "#"
HEREDOC_START_CHARACTER = "<"
CARRIAGE_RETURN_LINE_BREAK = "\r\n"
CARRIAGE_RETURN = "\r"
LINE_FEED = "\n"
END_OF_OPTIONS_PREFIX = "-- "
NESTED_LINE_BREAK_JOIN = ";"
ALL_CLOSING_CHARACTERS = SUBSHELL_CLOSE_TOKEN + NESTED_LINE_BREAK_JOIN
SUBSTITUTION_KEY_IGNORED_PATTERN = re.compile(r"[\s\\\"']")
SINGLE_QUOTE_INSIDE_SINGLE_QUOTES = "'\\''"
ALL_ANSI_C_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "e": "\x1b",
    "E": "\x1b",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
DOUBLE_QUOTED_ESCAPE_PATTERN = re.compile(r'[\\"]')
DOUBLE_QUOTED_ESCAPE_REPLACEMENT = r"\\\g<0>"
DOUBLE_QUOTED_SPECIAL_PATTERN = re.compile(r'[\\"]|\$\(')
ESCAPED_PAIR_LENGTH = 2
ESCAPED_SUBSTITUTION_OPENER = "\\$("
ESCAPED_SUBSTITUTION_WORD = "\\$\\("
SHORT_HEAD_OPTION = "-H"
LONG_HEAD_OPTION = "--head"
LONG_OPTION_PREFIX = "--"
OPTION_VALUE_SEPARATOR = "="
GH_PR_CREATE_PATTERN = re.compile(r"(?:^|[\s;&|(])gh(?:\.exe)?\s+pr\s+create\b(?P<rest>[^;&|]*)")
PULL_REQUEST_SCRIPT_CREATE_PATTERN = re.compile(
    r"pull_request\.py[\"']?\s+create\b(?P<rest>[^;&|]*)"
)
LOOSE_GH_PROGRAM_PATTERN = re.compile(r"(?<![\w.-])gh(?:\.exe)?(?![\w.-])")
LOOSE_OPEN_WORD_PATTERN = re.compile(r"(?<![\w-])(?:create|new)(?![\w-])")
LOOSE_OPEN_OR_MERGE_WORD_PATTERN = re.compile(r"(?<![\w-])(?:create|new|merge)(?![\w-])")
LOOSE_PULL_REQUEST_SCRIPT_PATTERN = re.compile(r"pull_request\.py")
HEAD_OPTION_PATTERN = re.compile(r"(?<!\S)(?:-H|--head)(?:=|\s+)[\"']?(?P<head>[^\s\"']+)")
BASE_OPTION_PATTERN = re.compile(r"(?<!\S)(?:-B(?:=|\s+)?|--base(?:=|\s+))[\"']?(?P<base>[^\s\"']+)")
BASE_OPTION_MENTION_PATTERN = re.compile(r"(?<!\S)(?:-[A-Za-z]*B|--base(?![\w-]))")
OPEN_REPOSITORY_OPTION_PATTERN = re.compile(
    r"(?<!\S)(?:-R(?:=|\s+)?|--repo(?:=|\s+))[\"']?(?P<repository>[^\s\"']+)"
)
REPOSITORY_OPTION_MENTION_PATTERN = re.compile(r"(?<!\S)(?:-[A-Za-z]*R|--repo(?![\w-]))")
ALL_LONE_CREATE_SUBCOMMANDS = (("pr", "create"), ("pr", "new"))
LONE_CREATE_SUBCOMMAND_WIDTH = 2
ALL_ROOT_REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
ALL_ROOT_REPOSITORY_JOINED_PREFIXES = ("--repo=", "-R")
ALL_SHELL_EXPANSION_CHARACTERS = frozenset("{}*?[")
TILDE_CHARACTER = "~"
EXTENDED_GLOB_OPENER_PATTERN = re.compile(r"[@+!]\(")
EXTENDED_GLOB_WORD_PATTERN = re.compile(r"[@+!](?:\(|$)")
ALL_SHELL_WORD_START_CHARACTERS = frozenset(";&|()<>")
ANSI_C_QUOTE_PREFIX = "$"
ANSI_C_NUMERIC_ESCAPE_PATTERN = re.compile(
    r"\\(?:x(?P<hex>[0-9A-Fa-f]{1,2})|u(?P<short_unicode>[0-9A-Fa-f]{1,4})"
    r"|U(?P<long_unicode>[0-9A-Fa-f]{1,8})|(?P<octal>[0-7]{1,3})|c(?P<control>.))",
    re.DOTALL,
)
ANSI_C_STRING_END_CHARACTER = "\0"
CONTROL_CHARACTER_MASK = 0x1F
BYTE_MASK = 0xFF
ASCII_MAXIMUM = 0x7F
OCTAL_BASE = 8
HEX_BASE = 16
SURROGATE_FIRST = 0xD800
SURROGATE_LAST = 0xDFFF
UNREADABLE_WORD_MARK = ""
QUOTED_EXPANSION_MARK = ""
ALL_EXPANSION_MARKS = frozenset({UNREADABLE_WORD_MARK, QUOTED_EXPANSION_MARK})
EXPANSION_START_CHARACTER = "$"
ALL_EXPANSION_OPENER_CHARACTERS = frozenset({EXPANSION_START_CHARACTER, "`"})
SPLITTING_PARAMETER_CHARACTER = "@"
PARAMETER_BRACE_OPEN = "{"
PARAMETER_BRACE_CLOSE = "}"
ALL_CREATE_TEXT_OPTIONS = frozenset(
    {
        "-t",
        "--title",
        "-b",
        "--body",
        "-F",
        "--body-file",
        "-l",
        "--label",
        "-r",
        "--reviewer",
        "-a",
        "--assignee",
        "-m",
        "--milestone",
        "-p",
        "--project",
        "-T",
        "--template",
    }
)
ALL_LONE_CREATE_REFUSED_CHARACTERS = frozenset("$`\n\r")
LONE_CREATE_UNQUOTED_REFUSED_CHARACTERS = "();<>|&#{}*?[~"
LONE_LAUNCHER_CREATE_WORD = "create"
LONE_LAUNCHER_LEAD_WIDTH = 2
LONE_LAUNCHER_PYTHON_PATTERN = re.compile(r"python3?")
LONE_LAUNCHER_OPTION_VALUE_SEPARATOR = "="
ALL_LONE_LAUNCHER_REQUIRED_OPTIONS = ("--repo", "--base", "--head")
ALL_LONE_LAUNCHER_VALUE_OPTIONS = frozenset({"--repo", "--base", "--head", "--title", "--body-file"})
ALL_LONE_LAUNCHER_FLAG_OPTIONS = frozenset({"--draft"})
LONE_LAUNCHER_OPTION_PREFIX = "-"
LAUNCHER_SCRIPT_FILE_NAME = "pull_request.py"
ALL_MANAGED_LAUNCHER_PATH_PARTS = (".agents", "skills", "pull-request", "scripts", LAUNCHER_SCRIPT_FILE_NAME)
MANAGED_LAUNCHER_HOME_PREFIX_PATTERN = re.compile(
    r"\A(?P<lead>\s*(?:python3?\s+)?)(?:~|\$HOME)(?="
    + re.escape("/" + "/".join(ALL_MANAGED_LAUNCHER_PATH_PARTS))
    + r"\s)"
)
HOME_EXPANSION_MARK = ""
HOME_VARIABLE_PATTERN = re.compile(r"\$HOME(?!\w)")
MARKED_MANAGED_LAUNCHER_WORD = "/".join((HOME_EXPANSION_MARK, *ALL_MANAGED_LAUNCHER_PATH_PARTS))
ALL_PUSH_REMOTE_BRANCH_KEYS = frozenset({"remote", "pushremote"})
ALL_ORIGIN_PUSH_KEYS = frozenset({"push", "pushurl"})
BRANCH_SETTING_SECTION = "branch"
MERGE_SETTING_KEY = "merge"
PUSH_DEFAULT_REMOTE_KEY = "pushdefault"
SETTINGS_LISTING_QUESTION = "merge review settings listing"
REMOTE_LISTING_QUESTION = "merge review remote listing"
ALL_MERGE_BASE_READ_ARGUMENTS = ("config", "--default", "", "--get")
MERGE_BASE_SETTING_TEMPLATE = "branch.{branch}.gh-merge-base"
ALL_SETTINGS_READ_ARGUMENTS = ("config", "--list", "--null")
SETTING_RECORD_END = "\0"
SETTING_NAME_END = "\n"
SETTING_PART_SEPARATOR = "."
REMOTE_SETTING_SECTION = "remote"
RESOLVED_REMOTE_SETTING_KEY = "gh-resolved"
RESOLVED_AS_BASE_VALUE = "base"
ORIGIN_REMOTE_NAME = "origin"
GITHUB_HOST = "github.com"
GH_HOST_VARIABLE = "GH_HOST"
REPOSITORY_PATH_SEPARATOR = "/"
OWNER_AND_REPO_PART_COUNT = 2
HOST_OWNER_AND_REPO_PART_COUNT = 3
CHANGE_FOLDER_PATTERN = re.compile(
    r"(?:^|[;&|(]\s*)(?:cd|pushd|Set-Location|sl)\s+(?:-Path\s+|-LiteralPath\s+)?"
    r"(?P<folder>\"[^\"]*\"|'[^']*'|[^\s;&|)]+)",
    re.IGNORECASE,
)
CREATE_TEXT_OPTION_PATTERN = re.compile(
    r"(?<!\S)(?:-t|--title|-b|--body|-F|--body-file)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
ORIGIN_URL_PATTERN = re.compile(
    r"github\.com[:/](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"
)
GIT_TIMEOUT_SECONDS = 3
REMOTE_LOOKUP_TIMEOUT_SECONDS = 5
GITHUB_REMOTE_URL_TEMPLATE = "https://github.com/{owner}/{repo}.git"
REMOTE_BRANCH_REFERENCE_TEMPLATE = "refs/heads/{branch}"
LS_REMOTE_FIELD_SEPARATOR = "\t"
ALL_NON_INTERACTIVE_GIT_SETTINGS = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
ALL_ORIGIN_URL_ARGUMENTS = ("remote", "get-url", "origin")
ORIGIN_URL_QUESTION = "merge review origin url"
OPEN_HEAD_PATTERN = re.compile(r"[0-9a-fA-F]{7,40}")
OPEN_RECEIPT_HEAD_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
REPOSITORY_SLUG_PATTERN = re.compile(r"[\w.-]+/[\w.-]+")
REMOTE_BRANCH_PREFIX = "origin/"
CURRENT_HEAD_REFERENCE = "HEAD"
OPEN_REVIEW_ANCESTOR_LIMIT = 100
ALL_STORED_HISTORY_GIT_SETTINGS = {"GIT_GRAFT_FILE": os.devnull, "GIT_NO_REPLACE_OBJECTS": "1"}
ALL_ANCESTRY_WALK_ARGUMENTS = ("rev-list", "--first-parent")
MAX_COUNT_OPTION_TEMPLATE = "--max-count={count}"
CONTAINS_OPTION_TEMPLATE = "--contains={commit}"
NO_CONTAINS_OPTION_TEMPLATE = "--no-contains={commit}"
ALL_BRANCH_REFERENCE_PREFIXES = ("refs/heads", "refs/remotes")
ALL_CHECKOUT_BRANCH_ARGUMENTS = ("symbolic-ref", "--quiet", "--short", "HEAD")
ALL_HOLDING_REFERENCE_ARGUMENTS = ("for-each-ref", "--format=%(refname)")
LOCAL_BRANCH_REFERENCE_TEMPLATE = "refs/heads/{branch}"
CURRENT_BRANCH_PLACEHOLDER = "<branch>"
REMOTE_TRACKING_REFERENCE_PREFIX = "refs/remotes/"
ORIGIN_TRACKING_REFERENCE_TEMPLATE = REMOTE_TRACKING_REFERENCE_PREFIX + ORIGIN_REMOTE_NAME + "/{branch}"
HEAD_OWNER_SEPARATOR = ":"
ALL_OUTSIDE_BASE_ARGUMENTS = ("rev-list", "--max-count=1")
EXCLUDE_FROM_WALK_OPTION = "--not"
ALL_MERGE_TREE_ARGUMENTS = ("merge-tree", "--stdin", "--write-tree")
MERGE_TREE_INPUT_TEMPLATE = "{base_commit} {commit}\n"
MERGE_TREE_FIELD_SEPARATOR = "\0"
MERGE_TREE_CONFLICTED_STATUS = "0"
MERGE_TREE_CLEAN_STATUS = "1"
ORIGIN_FETCH_DEFAULT_REFSPEC = "+refs/heads/*:refs/remotes/origin/*"
FETCH_SETTING_KEY = "fetch"
REFSPEC_SIDE_SEPARATOR = ":"
REFSPEC_GLOB_CHARACTER = "*"
ORIGIN_TRACKING_NAMESPACE = "refs/remotes/origin/"
FETCH_SETTINGS_UNREAD_TEXT = "the fetch settings, which git could not list"
NO_ORIGIN_FETCH_TEXT = "no `remote.origin.fetch` setting"
FETCH_REFSPEC_TEMPLATE = "`{refspec}`"
FETCH_REFSPEC_JOIN = ", "
ALL_VERIFY_OBJECT_ARGUMENTS = ("rev-parse", "--verify", "--quiet")
TREE_OF_COMMIT_TEMPLATE = "{commit}^{{tree}}"
COMMIT_OBJECT_TEMPLATE = "{commit}^{{commit}}"

GH_PR_MERGE_PATTERN = re.compile(r"(?:^|[\s;&|(])gh(?:\.exe)?\s+pr\s+merge\b(?P<rest>[^;&|]*)")
GH_API_MERGE_PATTERN = re.compile(
    r"(?:^|[\s;&|(])gh(?:\.exe)?\s+api\b[^;&|]*?repos/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pulls/(?P<number>\d+)/merge\b"
)
PR_NUMBER_PATTERN = re.compile(r"(?:^|\s)#?(?P<number>\d+)(?:\s|$)")
PR_URL_PATTERN = re.compile(
    r"github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pull/(?P<number>\d+)"
)
RULINGS_LINK_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pull/(?P<number>\d+)"
    r"#issuecomment-\d+"
)
FILED_ISSUE_LINK_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/issues/(?P<number>\d+)"
)
RULING_PATH_SEGMENT = r"(?!\.{1,2}(?![^\x00-\x1f:,/\\]))[^\x00-\x1f:,/\\]+"
RULING_REFERENCE_PATTERN = re.compile(
    r"(?P<path>" + RULING_PATH_SEGMENT + r"(?:/" + RULING_PATH_SEGMENT + r")*):(?P<line>[1-9]\d*)"
)
RULING_SEPARATOR = ","
RULING_LOOKUP_TIMEOUT_SECONDS = 10
GITHUB_API_READ_TIMEOUT_SECONDS = 20
GITHUB_API_CLIENT_NAME = "gh"
GITHUB_API_SUBCOMMAND = "api"
GITHUB_API_HOST_OPTION = "--hostname"
GITHUB_API_HOST = "github.com"
FILED_ISSUE_API_PATH_TEMPLATE = "repos/{owner}/{repo}/issues/{number}"
FILED_ISSUE_PAGE_KEY = "html_url"
FILED_ISSUE_PULL_REQUEST_KEY = "pull_request"
PULL_REQUEST_COMMITS_API_PATH_TEMPLATE = (
    "repos/{owner}/{repo}/pulls/{number}/commits?per_page=100&page={page}"
)
PULL_REQUEST_COMMITS_PAGE_SIZE = 100
PULL_REQUEST_COMMITS_PAGE_LIMIT = 3
EARLIER_COMMIT_READ_LIMIT = 40
GITHUB_COUNT_DEADLINE_SECONDS = 120
COMMIT_STATUSES_API_PATH_TEMPLATE = "repos/{owner}/{repo}/commits/{sha}/statuses?per_page=100"
COMMIT_SHA_KEY = "sha"
MERGE_REVIEW_STATUS_CONTEXT = "Merge review"
FAILED_REVIEW_STATUS_STATE = "failure"
REVIEW_STATUS_CREATOR_TYPE = "Bot"
REVIEW_STATUS_APP_LOGIN = "repo-rulefile-sync[bot]"
REVIEW_STATUS_RUN_PAGE_PATTERN = re.compile(
    r"https://github\.com/(?P<repository>[\w.-]+/[\w.-]+)/actions/runs/(?P<run_id>\d+)",
    re.IGNORECASE,
)
REVIEW_RUN_API_PATH_TEMPLATE = "repos/{repository}/actions/runs/{run_id}"
REVIEW_RUN_WORKFLOW_FILE = "efficient-review.yml"
REVIEW_RUN_TITLE_TEMPLATE = r"Merge review {repository}#(?:{number})? {head} base \S+"
REVIEW_RUN_COMPLETED_STATUS = "completed"
REVIEW_RUN_SUCCESS_CONCLUSION = "success"
RUN_ID_KEY = "id"
RUN_PATH_KEY = "path"
RUN_STATUS_KEY = "status"
RUN_CONCLUSION_KEY = "conclusion"
RUN_TITLE_KEY = "display_title"
STATUS_CONTEXT_KEY = "context"
STATUS_STATE_KEY = "state"
STATUS_CREATOR_KEY = "creator"
STATUS_TARGET_URL_KEY = "target_url"
CREATOR_TYPE_KEY = "type"
CREATOR_LOGIN_KEY = "login"
REPO_OPTION_PATTERN = re.compile(r"(?:-R|--repo)[\s=](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)")
MATCH_HEAD_PATTERN = re.compile(r"--match-head-commit[\s=](?P<sha>[0-9a-fA-F]{7,40})")
API_SHA_FIELD_PATTERN = re.compile(
    r"(?:-f|-F|--field|--raw-field)[\s=]sha=(?P<sha>[0-9a-fA-F]{7,40})"
)
ALL_OPTIONS_WITH_VALUE = (
    "-R",
    "--repo",
    "--match-head-commit",
    "-t",
    "--subject",
    "-b",
    "--body",
    "-F",
    "--body-file",
    "-A",
    "--author-email",
)
OPTION_WITH_VALUE_PATTERN = re.compile(
    r"(?<!\S)(?:" + "|".join(ALL_OPTIONS_WITH_VALUE) + r")"
    r"(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
AUTO_OPTION_PATTERN = re.compile(r"(?:^|\s)--auto(?:\s|$)")
DISABLE_AUTO_OPTION = "--disable-auto"
AUTO_OPTION = "--auto"
ALL_AUTO_FLAG_VALUE_PREFIXES = (AUTO_OPTION + "=", DISABLE_AUTO_OPTION + "=")
END_OF_OPTIONS_WORD = "--"
SHORT_OPTION_PREFIX = "-"
GH_PR_MERGE_CALL_PATTERN = re.compile(r"\bgh(?:\.exe)?\s+pr\s+merge\b")
GH_PROGRAM_WORD_PATTERN = re.compile(r"(?:^|[/\\])gh(?:\.exe)?$")
ALL_GH_PR_MERGE_SUBCOMMAND_WORDS = ("pr", "merge")
SHELL_PUNCTUATION_CHARACTERS = "();<>|&`\n"
SHELL_WHITESPACE_CHARACTERS = " \t\r"
SHELL_WORD_SEPARATOR = " "
SHELL_QUOTED_TEXT_PATTERN = re.compile(r"\\.|'[^']*'|\"(?:\\.|[^\"\\])*\"", re.DOTALL)
SHELL_QUOTED_TEXT_PLACEHOLDER = "_"
SHELL_COMMENT_START_PATTERN = re.compile(r"(?:^|[\s();<>|&`])#")

EXEMPT_REPOSITORIES_ENVIRONMENT_VARIABLE = "CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES"
REVIEW_COMMAND_ENVIRONMENT_VARIABLE = "CLAUDE_MERGE_REVIEW_COMMAND"
DEFAULT_REVIEW_COMMAND = "/code-review high --max-findings all"
RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE = "CLAUDE_MERGE_REVIEW_RECEIPT_DIR"
ALL_RECEIPT_DIRECTORY_SEGMENTS = (".claude", "merge-reviews")
RECEIPT_FILE_NAME_TEMPLATE = "{owner}__{repo}__{number}.json"
OPEN_RECEIPT_DIRECTORY_NAME = "heads"
OPEN_RECEIPT_FILE_NAME_TEMPLATE = "{owner}__{repo}__{head}.json"
OPEN_RECEIPT_GLOB_TEMPLATE = "*__{repo}__*.json"
OPEN_TARGET_WORD = "open"
REPOSITORY_SEPARATOR = ","
RECEIPT_HEAD_KEY = "head"
RECEIPT_BRANCH_KEY = "branch"
RECEIPT_FINDINGS_KEY = "findings"
RECEIPT_RULED_OUT_KEY = "ruled_out"
RECEIPT_RULINGS_KEY = "rulings"
RECEIPT_RULING_LINES_KEY = "ruling_lines"
RECEIPT_PASS_KEY = "pass"
RECEIPT_FILED_KEY = "filed"
FULL_REVIEW_PASS_COUNT = 3
RECORD_COMMAND = "python3 ~/.claude/scripts/merge_review_receipt.py"

NO_CLEAN_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} has no clean review on the head you are merging. Run the review "
    "loop, three full passes with fixes: review the pull request head with "
    "`{review_command}`, fix and push every finding, record the pass, and review the new "
    "head. Rule a finding out only with file:line evidence. A pass that reports zero "
    "findings, or rules out every one, is clean: record it with `"
    + RECORD_COMMAND
    + " {slug} {number} <head sha> <finding count>`, adding `--ruled-out <finding count> "
    "--rulings <link to the rulings comment on this pull request>` when every finding is "
    "ruled out. After the third pass, review the new head with `/code-review low {number}`, "
    "which names the pull request so the diff covers its base. If that pass still reports "
    "findings, do not loop again: file one issue in {slug} that lists them, record the pass "
    "with `--filed <issue url>`, and merge. Fix a security finding in this pull request or "
    "rule it out with evidence; never file it. Then merge pinned to the recorded head."
)
UNPINNED_MERGE_REASON_TEMPLATE = (
    "{slug}#{number} has a recorded review that lets the merge go on at {head}, but this "
    "merge names no head. Pass expectedHeadSha (merge tool) or --match-head-commit "
    "(gh pr merge) set to {head}, so a push after the review cannot ride the merge."
)
STALE_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} was reviewed at {head}, and this merge names {pinned}. "
    "Review the new head, record that pass, then merge pinned to it."
)
AUTO_MERGE_REASON_TEMPLATE = (
    "Auto-merge on {slug}#{number} names no head, so it could merge a head no review "
    "has seen. Run `gh pr merge {number} --repo {slug} --auto --match-head-commit {head}`, "
    "which arms auto-merge or joins the merge queue only while the head is {head}."
)
UNKNOWN_TARGET_REASON = (
    "This merge names no repository and pull request number the review gate can read. "
    "Name both, such as `gh pr merge 12 --repo owner/name --match-head-commit <sha>`."
)
NO_CLEAN_OPEN_REVIEW_REASON_TEMPLATE = (
    "{slug} has no clean review for head {head}, which this pull request would open with, "
    "and no review pass on a commit before it on this branch. Run one review pass on the "
    "branch diff with `{review_command}`, and `/security-review` where it is installed, then "
    "record that pass with `"
    + RECORD_COMMAND
    + " {slug} "
    + OPEN_TARGET_WORD
    + " <reviewed head sha> <finding count>`. Fix each valid finding in a new commit on top "
    "of the reviewed head, then open the pull request: the fix commits need no second pass. "
    "A pass with zero findings opens at the reviewed head itself, and so does a pass whose "
    "every finding is ruled out with `--ruled-out <finding count> --rulings <path:line for "
    "each finding, comma separated>`, each path:line a line this head holds. A merge pinned "
    "to {head} accepts an open pass only at zero findings."
)
FINDINGS_AT_HEAD_REASON_TEMPLATE = (
    "{slug} has no clean review for head {head}, which this pull request would open with. "
    "A review pass on {head}, this head itself, is recorded with {finding_count} findings, so "
    "the fixes come next. Fix each valid finding in a new commit on top of {head}, push the "
    "branch with `git push origin HEAD:refs/heads/{branch}`, then open the pull request again: "
    "the fix commits need no second pass. When the fix commits are already made, push them: "
    "gh and the create pull request tool open the pull request at the head GitHub holds, and "
    "the gate reads that head."
)
BRANCHLESS_PASS_REASON_TEMPLATE = (
    "{slug} has no clean review for head {head}, which this pull request would open with. "
    "A review pass on {reviewed}, a commit before it on this branch, is recorded with "
    "{finding_count} findings and no branch, because it was recorded outside a checkout of "
    "`{branch}`: in another folder, on a detached HEAD, or while another branch held "
    "{reviewed}. A pass with no branch counts only at its own head, so the fix commits on top "
    "get no credit yet. Record it again from the checkout of `{branch}`, with `{branch}` "
    "checked out: `"
    + RECORD_COMMAND
    + " {slug} "
    + OPEN_TARGET_WORD
    + " {reviewed} {finding_count}`, then open again. No new review pass is needed. When the "
    "script still says it records no branch, another branch holds {reviewed}; its output "
    "names the step."
)
EXPANDED_WORDS_REASON = (
    "This pull request create has a word bash expands before gh runs, so the gate cannot tell "
    "which head, base or repository gh reads: a `$` or backtick expansion in a flag, or in a value "
    "of `--head`, `--base` or `--repo`, "
    "or, outside quotes in any word, a `$` or backtick expansion, a brace, a glob character "
    "(* ? [), an extended glob such as @(x) or a word that starts with ~. Write each flag as a "
    "plain word with a plain value, such as `--base main` or `--head feature`. Put title and body "
    "text in quotes, or pass the body with `--body-file <file>`, then open again."
)
UNSETTLED_HEAD_REASON_TEMPLATE = (
    "{slug} has a clean review for head {head}, and this pull request create shares its command "
    "with a step the gate does not count as settled, such as a `git push`, a file write, a "
    "process substitution or a pipe into the create, that runs before the create or beside it. "
    "That step may move the head, the branch or the repository after the gate reads it, so the "
    "review does not cover the head gh opens. Run the other steps first, then run the create on "
    "its own. Before it, the command may hold only `cd` or `pushd` with one plain folder outside "
    ".git, or a bare `cat`, `echo`, `printf`, `head` or `tail` that writes no file. Title and "
    "body substitutions may run only `cat`, `echo` or `printf`, with a quoted heredoc delimiter, "
    "and no `$[`, `$((` or substring offset arithmetic may appear outside single quotes. "
    "Output may go only to /dev/null, to a plain file outside .git, or through a pipe into "
    "`cat`, `head`, `tail`, `tee` or `grep`."
)
WITHHELD_CREDIT_REASON_PREFIX = (
    "{slug} has no clean review for head {head}, which this pull request would open with. "
    "A review pass on {reviewed}, a commit before it on this branch, is recorded, and it gives "
    "this open no credit because "
)
UNREAD_FLAG_CAUSE = (
    "the create names a `--base` or `--repo` value the gate cannot read, or a repository on a "
    "host other than github.com. Name one `--base <branch>`, and `--repo owner/name` when needed."
)
OTHER_HOST_CAUSE = (
    "`GH_HOST` is {host}, and an earlier pass gives credit only to an open on github.com. "
    "Unset `GH_HOST` or set it to github.com."
)
SESSION_REPOSITORY_CAUSE = (
    "`GH_REPO` is {session_repository}, which names a repository other than {slug}. Unset "
    "`GH_REPO` or set it to {slug}."
)
NOT_LONE_CAUSE = (
    "the create is not the whole command. Run `gh pr create` as its own command, with no `cd`, "
    "variable prefix or other command beside it. Put a `--repo` before `pr` or after `create`, "
    "never between them. Write `gh`, `python` or `python3` as a bare name that bash finds on "
    "PATH, never by a path such as `./gh` or `/tmp/x/python3`. The `pull_request.py create` "
    "launcher counts too when it runs alone "
    "as `~/.agents/skills/pull-request/scripts/pull_request.py`, written with `~/`, `$HOME/` or "
    "the full home folder, with `--repo`, `--base` and `--head`; another script with that name "
    "does not count. Outside quotes, any of ( ) ; < > | "
    "& # {{ }} * ? [ ~ counts as another word, and a $, a backtick or a line break counts "
    "anywhere, so quote title text, put the body in a file passed with `--body-file`, or open "
    "with the create pull request tool and set its `base`."
)
NO_BASE_OR_BRANCH_CAUSE = (
    "the gate could read neither a `--base` nor the checkout branch. Name the base with "
    "`--base <branch>`."
)
OTHER_REMOTE_CAUSE = (
    "this checkout has a remote other than origin, or a `gh-resolved` setting other than "
    "`base`, so gh may open in another repository. Pass `--repo {slug}`."
)
TOOL_NO_BASE_CAUSE = (
    "the create pull request tool call names no base. Set its `base` field to the branch the "
    "pull request merges into."
)
UNKNOWN_PUSH_TARGET_CAUSE = (
    "this create names no `--head`, and gh may send the checkout branch `{branch}` to another "
    "branch name or repository than the `{branch}` the gate read on {slug}: a "
    "`branch.{branch}.merge` other than `refs/heads/{branch}`, a `branch.{branch}.remote`, "
    "`branch.{branch}.pushRemote` or `remote.pushDefault` other than origin, a "
    "`remote.origin.push` or `remote.origin.pushurl` setting, a `--repo` that origin does not "
    "name, or git settings the gate could not read. Name the head with `--head {branch}`, then "
    "open again."
)
UNKNOWN_PUSH_TARGET_REASON_TEMPLATE = (
    "{slug} has a clean review for head {head}, and " + UNKNOWN_PUSH_TARGET_CAUSE
)
HEAD_UNREAD_CAUSE = (
    "the gate could not read the head branch `{branch}` on GitHub, so it cannot tell that the "
    "commit this clone holds is the tip GitHub opens the pull request with. Check that the "
    "branch is pushed and that `git ls-remote https://github.com/{slug}.git {branch}` answers "
    "from this session, running `gh auth setup-git` when git has no GitHub sign-in, then open "
    "again."
)
BASE_UNREAD_CAUSE = (
    "the gate could not read the base {base} of {slug} on GitHub. Check that the branch is "
    "there and that this session reaches github.com, then open again."
)
NAMED_BASE_TEMPLATE = "`{base}`"
GH_PICKED_BASE_TEMPLATE = "(the `gh-merge-base` setting of `{branch}`, or the default branch)"
BRANCHES_UNREAD_CAUSE = (
    "the gate could not list the branches that hold {reviewed}. Open again once git answers."
)
HELD_BY_OTHER_REFERENCE_CAUSE = (
    "{reference} holds {reviewed} without this head, so the pass may cover that line and not "
    "this branch. An earlier pass gives credit only while no other branch holds the reviewed "
    "commit without the head. Delete {reference} or move it to this head when it is a copy of "
    "this branch."
)
MAPPED_TRACKING_REFERENCE_CAUSE = (
    "{reference} holds {reviewed} without this head, and this clone fetches with {refspec}, "
    "not with the clone default `" + ORIGIN_FETCH_DEFAULT_REFSPEC + "` alone, so another branch "
    "may be written onto that name. Set `git config --replace-all remote.origin.fetch '"
    + ORIGIN_FETCH_DEFAULT_REFSPEC
    + "'`, drop any other remote's refspec that writes under `"
    + ORIGIN_TRACKING_NAMESPACE
    + "`, fetch, then open again."
)
LOCAL_BRANCH_BEHIND_CAUSE = (
    "your local branch `{branch}` is behind this head: it still sits on {reviewed} and lacks "
    "the fix commits, so the gate cannot tell it from another line. Fast-forward it with "
    "`git merge --ff-only {head}` while `{branch}` is checked out, or `git branch -f {branch} "
    "{head}` when it is not, then open again."
)
INSIDE_BASE_CAUSE = (
    "the base on GitHub already holds {reviewed}, so the pass covered base work. Run one review "
    "pass on the branch diff with `{review_command}`, record it, then open again."
)
NO_CONTENT_ADDED_CAUSE = (
    "the base on GitHub already holds the content of {reviewed}, such as from a squash merge, "
    "so the pass covered base work. Run one review pass on the branch diff with "
    "`{review_command}`, record it, then open again."
)
PREFIX_ORIGIN_CHECK_SENTENCE = (
    " This create names its repository only with a `GH_REPO=` prefix, and a wrapper such as "
    "`env -u GH_REPO` can drop that prefix before gh runs, so the gate also checks the origin "
    "repository. Name the repository with `--repo owner/name` on the create instead."
)
FETCH_BASE_COMMAND = "git fetch origin"
FETCH_NAMED_BASE_COMMAND_TEMPLATE = FETCH_BASE_COMMAND + " {base}"
MISSING_BASE_COMMIT_REASON_TEMPLATE = (
    "{slug} has a review pass on a commit before this head, but the base branch on GitHub is at "
    "{base_commit}, which this clone has not fetched, so the gate cannot tell whether the base "
    "already holds the reviewed work. Fetch the base from {slug}, with `{fetch_command}` when "
    "origin is that repository, then open the pull request again."
)
UNKNOWN_OPEN_TARGET_REASON = (
    "This pull request names no repository or head commit the review gate can read. Check that "
    "the head branch is on GitHub and this session can reach it, or run it from the branch "
    "checkout, or pass `--repo owner/name` and `--head <pushed branch>`."
)
