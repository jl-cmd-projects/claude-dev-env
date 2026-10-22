"""Named constants for merge_review_gate, the clean-review open and merge gate."""

from __future__ import annotations

import re

HOOK_EVENT_NAME = "PreToolUse"
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

GH_PR_CREATE_PATTERN = re.compile(r"(?:^|[\s;&|(])gh(?:\.exe)?\s+pr\s+create\b(?P<rest>[^;&|]*)")
PULL_REQUEST_SCRIPT_CREATE_PATTERN = re.compile(
    r"pull_request\.py[\"']?\s+create\b(?P<rest>[^;&|]*)"
)
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
REPO_OPTION_PATTERN = re.compile(r"(?:-R|--repo)[\s=](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)")
MATCH_HEAD_PATTERN = re.compile(r"--match-head-commit[\s=](?P<sha>[0-9a-fA-F]{7,40})")
API_SHA_FIELD_PATTERN = re.compile(r"(?:-f|-F|--field|--raw-field)[\s=]sha=(?P<sha>[0-9a-fA-F]{7,40})")
OPTION_WITH_VALUE_PATTERN = re.compile(
    r"(?<!\S)(?:-R|--repo|--match-head-commit|-t|--subject|-b|--body|-F|--body-file|-A|--author-email)"
    r"(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
AUTO_OPTION_PATTERN = re.compile(r"(?:^|\s)--auto(?:\s|$)")

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
    "again until a pass reports zero findings. Record that pass with `"
    + RECORD_COMMAND
    + " {slug} "
    + OPEN_TARGET_WORD
    + " {head} 0`, then open the pull request. The merge accepts that receipt while the "
    "head stays {head}."
)
UNKNOWN_OPEN_TARGET_REASON = (
    "This pull request names no repository or head commit the review gate can read. Run it "
    "from the branch checkout, or pass `--repo owner/name` and `--head <pushed branch>`."
)
