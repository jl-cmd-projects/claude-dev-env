"""Deny an agent's merge until a review of the merged head came back clean.

The agent that drives a pull request loops a code review on it, fixing and
pushing each finding, until one pass reports zero findings. The merge then
names that exact head::

    merge, receipt says 0 findings at abc123, merge pinned to abc123 -> allow
    merge, receipt at abc123, merge pinned to def456                 -> deny, review again
    merge, receipt at abc123, merge names no head                    -> deny, pin it
    merge, no receipt or the receipt counts findings                 -> deny, run the loop
    auto-merge or enqueue pinned to the clean head                    -> allow
    auto-merge that names no head                                     -> deny, pin it
    repository listed in CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES      -> allow

The deny reason names the review command CLAUDE_MERGE_REVIEW_COMMAND sets,
or ``/code-review high --max-findings all`` when it is unset.

``scripts/merge_review_receipt.py`` writes the receipt this reads.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.merge_review_gate_constants import (
    ALL_RECEIPT_DIRECTORY_SEGMENTS,
    ALL_SHELL_TOOL_NAMES,
    AUTO_MERGE_REASON_TEMPLATE,
    AUTO_MERGE_TOOL_SUFFIX,
    API_SHA_FIELD_PATTERN,
    AUTO_OPTION_PATTERN,
    DEFAULT_REVIEW_COMMAND,
    DENY_DECISION,
    EXEMPT_REPOSITORIES_ENVIRONMENT_VARIABLE,
    EXPECTED_HEAD_FIELD,
    GH_API_MERGE_PATTERN,
    GH_PR_MERGE_PATTERN,
    HOOK_EVENT_NAME,
    MATCH_HEAD_PATTERN,
    MERGE_TOOL_SUFFIX,
    NO_CLEAN_REVIEW_REASON_TEMPLATE,
    NUMBER_FIELD,
    OPTION_WITH_VALUE_PATTERN,
    OWNER_FIELD,
    PERMISSION_DECISION_REASON_KEY,
    PR_NUMBER_PATTERN,
    PR_URL_PATTERN,
    RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE,
    RECEIPT_FILE_NAME_TEMPLATE,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
    REPOSITORY_SEPARATOR,
    REVIEW_COMMAND_ENVIRONMENT_VARIABLE,
    STALE_REVIEW_REASON_TEMPLATE,
    UNKNOWN_TARGET_REASON,
    UNPINNED_MERGE_REASON_TEMPLATE,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


@dataclass(frozen=True)
class MergeRequest:
    """One merge a tool call asks for.

    Attributes:
        owner: Repository owner, or empty when the call names none.
        repo: Repository name, or empty when the call names none.
        number: Pull request number, or None when the call names none.
        pinned_head: The head the merge is pinned to, or None.
        is_auto_merge: Whether the call turns on auto-merge.
    """

    owner: str
    repo: str
    number: int | None
    pinned_head: str | None
    is_auto_merge: bool

    @property
    def slug(self) -> str:
        """Return ``owner/repo``."""
        return f"{self.owner}/{self.repo}"


def receipt_directory() -> Path:
    """Return the folder that holds one review receipt per pull request.

    Returns:
        The folder CLAUDE_MERGE_REVIEW_RECEIPT_DIR names, else ``~/.claude/merge-reviews``.
    """
    override = os.environ.get(RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override)
    return Path.home().joinpath(*ALL_RECEIPT_DIRECTORY_SEGMENTS)


def receipt_path(owner: str, repo: str, number: int) -> Path:
    """Return where the review receipt for one pull request lives.

    Args:
        owner: Repository owner.
        repo: Repository name.
        number: Pull request number.

    Returns:
        The receipt file path.
    """
    return receipt_directory() / RECEIPT_FILE_NAME_TEMPLATE.format(
        owner=owner.casefold(), repo=repo.casefold(), number=number
    )


def merge_request_from(all_payload_fields: dict[str, object]) -> MergeRequest | None:
    """Read the merge a PreToolUse payload asks for.

    ::

        mcp__github__merge_pull_request {owner, repo, pullNumber, expectedHeadSha}
        mcp__github__enable_pr_auto_merge {owner, repo, pullNumber}
        gh pr merge 12 --repo o/r --match-head-commit abc123
        gh api repos/o/r/pulls/12/merge -X PUT

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The merge request, or None when the call merges nothing.
    """
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if tool_name.endswith((MERGE_TOOL_SUFFIX, AUTO_MERGE_TOOL_SUFFIX)):
        return _tool_merge_request(tool_name, tool_input)
    command = tool_input.get("command")
    if tool_name not in ALL_SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    return _shell_merge_request(command)


def _tool_merge_request(tool_name: str, all_tool_input: dict[object, object]) -> MergeRequest:
    number = all_tool_input.get(NUMBER_FIELD)
    pinned_head = all_tool_input.get(EXPECTED_HEAD_FIELD)
    return MergeRequest(
        owner=str(all_tool_input.get(OWNER_FIELD, "")),
        repo=str(all_tool_input.get(REPO_FIELD, "")),
        number=int(number) if isinstance(number, (int, float)) else None,
        pinned_head=pinned_head if isinstance(pinned_head, str) and pinned_head else None,
        is_auto_merge=tool_name.endswith(AUTO_MERGE_TOOL_SUFFIX),
    )


def _shell_merge_request(command: str) -> MergeRequest | None:
    api_match = GH_API_MERGE_PATTERN.search(command)
    if api_match:
        return MergeRequest(
            owner=api_match["owner"],
            repo=api_match["repo"],
            number=int(api_match["number"]),
            pinned_head=_api_pinned_head(command),
            is_auto_merge=False,
        )
    merge_match = GH_PR_MERGE_PATTERN.search(command)
    if not merge_match:
        return None
    rest = merge_match["rest"]
    owner, repo, number = _gh_pr_merge_target(rest)
    head_match = MATCH_HEAD_PATTERN.search(rest)
    return MergeRequest(
        owner=owner,
        repo=repo,
        number=number,
        pinned_head=head_match["sha"] if head_match else None,
        is_auto_merge=bool(AUTO_OPTION_PATTERN.search(rest)),
    )


def _gh_pr_merge_target(arguments: str) -> tuple[str, str, int | None]:
    url_match = PR_URL_PATTERN.search(arguments)
    if url_match:
        return url_match["owner"], url_match["repo"], int(url_match["number"])
    repo_match = REPO_OPTION_PATTERN.search(arguments)
    number_match = PR_NUMBER_PATTERN.search(_without_option_values(arguments))
    return (
        repo_match["owner"] if repo_match else "",
        repo_match["repo"] if repo_match else "",
        int(number_match["number"]) if number_match else None,
    )


def _api_pinned_head(command: str) -> str | None:
    sha_match = API_SHA_FIELD_PATTERN.search(command)
    return sha_match["sha"] if sha_match else None


def _without_option_values(arguments: str) -> str:
    return OPTION_WITH_VALUE_PATTERN.sub(" ", arguments)


def _is_exempt(request: MergeRequest) -> bool:
    listed = os.environ.get(EXEMPT_REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    all_exempt = {
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    }
    return request.slug.casefold() in all_exempt


def _clean_head(request: MergeRequest) -> str | None:
    if request.number is None:
        return None
    try:
        receipt = json.loads(
            receipt_path(request.owner, request.repo, request.number).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(receipt, dict) or receipt.get(RECEIPT_FINDINGS_KEY) != 0:
        return None
    head = receipt.get(RECEIPT_HEAD_KEY)
    return head if isinstance(head, str) and head else None


def _review_command() -> str:
    return os.environ.get(REVIEW_COMMAND_ENVIRONMENT_VARIABLE) or DEFAULT_REVIEW_COMMAND


def _same_commit(first: str, second: str) -> bool:
    shorter, longer = sorted((first.casefold(), second.casefold()), key=len)
    return longer.startswith(shorter)


def deny_reason(request: MergeRequest) -> str | None:
    """Return why a merge must wait for a clean review, or None to allow it.

    Args:
        request: The merge the tool call asks for.

    Returns:
        The deny reason, or None when the merge may run.
    """
    if not request.owner or not request.repo or request.number is None:
        return UNKNOWN_TARGET_REASON
    if _is_exempt(request):
        return None
    fields = {"slug": request.slug, "number": request.number}
    clean_head = _clean_head(request)
    if clean_head is None:
        return NO_CLEAN_REVIEW_REASON_TEMPLATE.format(review_command=_review_command(), **fields)
    if request.pinned_head is None and request.is_auto_merge:
        return AUTO_MERGE_REASON_TEMPLATE.format(head=clean_head, **fields)
    if request.pinned_head is None:
        return UNPINNED_MERGE_REASON_TEMPLATE.format(head=clean_head, **fields)
    if not _same_commit(clean_head, request.pinned_head):
        return STALE_REVIEW_REASON_TEMPLATE.format(
            head=clean_head, pinned=request.pinned_head, **fields
        )
    return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny decision for a merge with no clean review, else None.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The hook output that denies the call, or None to allow it.
    """
    request = merge_request_from(all_payload_fields)
    if request is None:
        return None
    reason = deny_reason(request)
    if reason is None:
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: reason,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
