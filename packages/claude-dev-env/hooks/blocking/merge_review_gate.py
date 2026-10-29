"""Deny an agent's pull request open or merge until a review of that head came back clean.

The agent reviews its branch before it opens the pull request, and loops a
code review on the pull request, fixing and pushing each finding, until one
pass reports zero findings or every finding it reports is ruled out with a
link to the posted rulings. The open and the merge then name that exact head::

    open, open receipt says 0 findings at abc123, branch head abc123 -> allow
    open, no open receipt for the branch head                        -> deny, review first
    merge, receipt says 0 findings at abc123, merge pinned to abc123 -> allow
    merge, open receipt clean at abc123, merge pinned to abc123      -> allow
    merge, receipt rules out all 3 findings with a link, pinned       -> allow
    merge, receipt at abc123, merge pinned to def456                 -> deny, review again
    merge, receipt at abc123, merge names no head                    -> deny, pin it
    merge, no receipt or the receipt counts open findings            -> deny, run the loop
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

from blocking.merge_review_gate_parts.open_request import OpenRequest, open_request_from
from blocking.merge_review_gate_parts.receipts import (
    has_clean_open_review,
    has_zero_finding_open_review,
    is_clean_receipt,
    receipt_path,
    same_commit,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.merge_review_gate_constants import (
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
    NO_CLEAN_OPEN_REVIEW_REASON_TEMPLATE,
    NO_CLEAN_REVIEW_REASON_TEMPLATE,
    NUMBER_FIELD,
    OPTION_WITH_VALUE_PATTERN,
    OWNER_FIELD,
    PERMISSION_DECISION_REASON_KEY,
    PR_NUMBER_PATTERN,
    PR_URL_PATTERN,
    RECEIPT_HEAD_KEY,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
    REPOSITORY_SEPARATOR,
    REVIEW_COMMAND_ENVIRONMENT_VARIABLE,
    STALE_REVIEW_REASON_TEMPLATE,
    UNKNOWN_OPEN_TARGET_REASON,
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


def open_deny_reason(request: OpenRequest) -> str | None:
    """Return why a pull request open must wait for a clean review, or None to allow it.

    Args:
        request: The open the tool call asks for.

    Returns:
        The deny reason, or None when the open may run.
    """
    if not request.owner or not request.repo:
        return UNKNOWN_OPEN_TARGET_REASON
    if _is_exempt(request.slug):
        return None
    if not request.head:
        return UNKNOWN_OPEN_TARGET_REASON
    if has_clean_open_review(request.repo, request.head):
        return None
    return NO_CLEAN_OPEN_REVIEW_REASON_TEMPLATE.format(
        slug=request.slug, head=request.head, review_command=_review_command()
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


def _is_exempt(slug: str) -> bool:
    listed = os.environ.get(EXEMPT_REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    all_exempt = {
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    }
    return slug.casefold() in all_exempt


def _numbered_receipt(request: MergeRequest) -> dict[str, object] | None:
    if request.number is None:
        return None
    try:
        receipt = json.loads(
            receipt_path(request.owner, request.repo, request.number).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return receipt if isinstance(receipt, dict) else None


def _receipt_head(all_receipt_fields: dict[str, object] | None) -> str | None:
    head = all_receipt_fields.get(RECEIPT_HEAD_KEY) if all_receipt_fields else None
    return head if isinstance(head, str) and head else None


def _clean_head(request: MergeRequest, all_receipt_fields: dict[str, object] | None) -> str | None:
    if all_receipt_fields is None or request.number is None:
        return None
    if not is_clean_receipt(all_receipt_fields, request.owner, request.repo, request.number):
        return None
    return _receipt_head(all_receipt_fields)


def _review_command() -> str:
    return os.environ.get(REVIEW_COMMAND_ENVIRONMENT_VARIABLE) or DEFAULT_REVIEW_COMMAND


def deny_reason(request: MergeRequest) -> str | None:
    """Return why a merge must wait for a clean review, or None to allow it.

    Args:
        request: The merge the tool call asks for.

    Returns:
        The deny reason, or None when the merge may run.
    """
    if not request.owner or not request.repo or request.number is None:
        return UNKNOWN_TARGET_REASON
    if _is_exempt(request.slug):
        return None
    numbered_receipt = _numbered_receipt(request)
    numbered_head = _receipt_head(numbered_receipt)
    pass_on_pinned_head = (
        numbered_head is not None
        and request.pinned_head is not None
        and same_commit(numbered_head, request.pinned_head)
    )
    if (
        request.pinned_head
        and not pass_on_pinned_head
        and has_zero_finding_open_review(request.repo, request.pinned_head)
    ):
        return None
    fields = {"slug": request.slug, "number": request.number}
    clean_head = _clean_head(request, numbered_receipt)
    if clean_head is None:
        return NO_CLEAN_REVIEW_REASON_TEMPLATE.format(review_command=_review_command(), **fields)
    if request.pinned_head is None and request.is_auto_merge:
        return AUTO_MERGE_REASON_TEMPLATE.format(head=clean_head, **fields)
    if request.pinned_head is None:
        return UNPINNED_MERGE_REASON_TEMPLATE.format(head=clean_head, **fields)
    if not same_commit(clean_head, request.pinned_head):
        return STALE_REVIEW_REASON_TEMPLATE.format(
            head=clean_head, pinned=request.pinned_head, **fields
        )
    return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny decision for an open or merge with no clean review, else None.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The hook output that denies the call, or None to allow it.
    """
    open_request = open_request_from(
        all_payload_fields, needs_head=lambda slug: not _is_exempt(slug)
    )
    merge_request = merge_request_from(all_payload_fields)
    reason = (open_deny_reason(open_request) if open_request is not None else None) or (
        deny_reason(merge_request) if merge_request is not None else None
    )
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
