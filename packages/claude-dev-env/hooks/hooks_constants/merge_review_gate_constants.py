"""Named constants for merge_review_gate, the clean-review merge gate."""

from __future__ import annotations

import re

HOOK_EVENT_NAME = "PreToolUse"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"

MERGE_TOOL_SUFFIX = "__merge_pull_request"
AUTO_MERGE_TOOL_SUFFIX = "__enable_pr_auto_merge"
ALL_SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

OWNER_FIELD = "owner"
REPO_FIELD = "repo"
NUMBER_FIELD = "pullNumber"
EXPECTED_HEAD_FIELD = "expectedHeadSha"

GH_PR_MERGE_PATTERN = re.compile(r"(?:^|[\s;&|(])gh(?:\.exe)?\s+pr\s+merge\b(?P<rest>[^;&|]*)")
GH_API_MERGE_PATTERN = re.compile(
    r"(?:^|[\s;&|(])gh(?:\.exe)?\s+api\b[^;&|]*?repos/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pulls/(?P<number>\d+)/merge\b"
)
PR_NUMBER_PATTERN = re.compile(r"(?:^|\s)#?(?P<number>\d+)(?:\s|$)")
PR_URL_PATTERN = re.compile(
    r"github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pull/(?P<number>\d+)"
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
RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE = "CLAUDE_MERGE_REVIEW_RECEIPT_DIR"
ALL_RECEIPT_DIRECTORY_SEGMENTS = (".claude", "merge-reviews")
RECEIPT_FILE_NAME_TEMPLATE = "{owner}__{repo}__{number}.json"
REPOSITORY_SEPARATOR = ","
RECEIPT_HEAD_KEY = "head"
RECEIPT_FINDINGS_KEY = "findings"
RECORD_COMMAND = "python3 ~/.claude/scripts/merge_review_receipt.py"

NO_CLEAN_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} has no clean review on the head you are merging. Run the review "
    "loop: review the pull request head, fix and push every finding, and review again "
    "until a pass reports zero findings. Record that pass with `"
    + RECORD_COMMAND
    + " {slug} {number} <head sha> 0`, then merge pinned to that head."
)
UNPINNED_MERGE_REASON_TEMPLATE = (
    "{slug}#{number} has a clean review for {head}, but this merge names no head. "
    "Pass expectedHeadSha (merge tool) or --match-head-commit (gh pr merge) set to "
    "{head}, so a push after the review cannot ride the merge."
)
STALE_REVIEW_REASON_TEMPLATE = (
    "{slug}#{number} was reviewed clean at {head}, and this merge names {pinned}. "
    "Review the new head until a pass reports zero findings, record it, then merge."
)
AUTO_MERGE_REASON_TEMPLATE = (
    "Auto-merge on {slug}#{number} merges a future head no review has seen. Run the "
    "review loop until it is clean, then merge directly, pinned to the reviewed head."
)
UNKNOWN_TARGET_REASON = (
    "This merge names no repository and pull request number the review gate can read. "
    "Name both, such as `gh pr merge 12 --repo owner/name --match-head-commit <sha>`."
)
