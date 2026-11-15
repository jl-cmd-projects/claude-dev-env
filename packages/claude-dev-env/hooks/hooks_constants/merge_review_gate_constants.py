"""Named constants for merge_review_gate, the clean-review open and merge gate."""

from __future__ import annotations

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
CWD_FIELD = "cwd"

ALL_HEAD_OPTIONS = frozenset({"-H", "--head"})
ALL_REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
LONG_REPOSITORY_OPTION = "--repo"
REPOSITORY_SHORT_LETTER = "R"
HEAD_SHORT_LETTER = "H"
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
RULING_PATH_SEGMENT = r"(?!\.{1,2}(?![^\x00-\x1f:,/\\]))[^\x00-\x1f:,/\\]+"
RULING_REFERENCE_PATTERN = re.compile(
    r"(?P<path>" + RULING_PATH_SEGMENT + r"(?:/" + RULING_PATH_SEGMENT + r")*):(?P<line>[1-9]\d*)"
)
RULING_SEPARATOR = ","
RULING_LOOKUP_TIMEOUT_SECONDS = 10
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
RECEIPT_FINDINGS_KEY = "findings"
RECEIPT_RULED_OUT_KEY = "ruled_out"
RECEIPT_RULINGS_KEY = "rulings"
RECEIPT_RULING_LINES_KEY = "ruling_lines"
RECORD_COMMAND = "python3 ~/.claude/scripts/merge_review_receipt.py"

NO_CLEAN_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} has no clean review on the head you are merging. Run the review "
    "loop: review the pull request head with `{review_command}`, fix and push every "
    "finding, and review again. After three full passes, each later pass is "
    "`/code-review low --fix {number}`, which names the pull request so the diff "
    "covers its base: commit and push its fixes, then review the new head. "
    "Repeat until a pass reports zero findings or every finding is ruled out with file:line "
    "evidence. Record that pass with `"
    + RECORD_COMMAND
    + " {slug} {number} <head sha> <finding count>`, adding `--ruled-out <finding count> "
    "--rulings <link to the rulings comment on this pull request>` when every finding is "
    "ruled out, then merge "
    "pinned to that head."
)
UNPINNED_MERGE_REASON_TEMPLATE = (
    "{slug}#{number} has a clean review for {head}, but this merge names no head. "
    "Pass expectedHeadSha (merge tool) or --match-head-commit (gh pr merge) set to "
    "{head}, so a push after the review cannot ride the merge."
)
STALE_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} was reviewed clean at {head}, and this merge names {pinned}. "
    "Review the new head until a pass reports zero findings or every finding is ruled "
    "out, record it, then merge."
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
    "{slug} has no clean review for head {head}, which this pull request would open with. "
    "Review the branch diff with `{review_command}`, fix and push every finding, and review "
    "again until a pass reports zero findings or every finding is ruled out with file:line "
    "evidence. Record a pass with zero findings with `"
    + RECORD_COMMAND
    + " {slug} "
    + OPEN_TARGET_WORD
    + " {head} 0`. Record a pass whose every finding is ruled out with `"
    + RECORD_COMMAND
    + " {slug} "
    + OPEN_TARGET_WORD
    + " {head} <finding count> --ruled-out <finding count> --rulings <path:line for each "
    "finding, comma separated>`, each path:line a line this head holds. Then open the pull "
    "request. A merge pinned to {head} accepts an open pass only at zero findings."
)
PREFIX_ORIGIN_CHECK_SENTENCE = (
    " This create names its repository only with a `GH_REPO=` prefix, and a wrapper such as "
    "`env -u GH_REPO` can drop that prefix before gh runs, so the gate also checks the origin "
    "repository. Name the repository with `--repo owner/name` on the create instead."
)
UNKNOWN_OPEN_TARGET_REASON = (
    "This pull request names no repository or head commit the review gate can read. Check that "
    "the head branch is on GitHub and this session can reach it, or run it from the branch "
    "checkout, or pass `--repo owner/name` and `--head <pushed branch>`."
)
