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
import subprocess
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
    CREATE_TOOL_SUFFIX,
    CURRENT_HEAD_REFERENCE,
    CWD_FIELD,
    DEFAULT_REVIEW_COMMAND,
    DENY_DECISION,
    EXEMPT_REPOSITORIES_ENVIRONMENT_VARIABLE,
    EXPECTED_HEAD_FIELD,
    GH_API_MERGE_PATTERN,
    GH_PR_CREATE_PATTERN,
    GH_PR_MERGE_PATTERN,
    GIT_TIMEOUT_SECONDS,
    HEAD_BRANCH_FIELD,
    HEAD_OPTION_PATTERN,
    HOOK_EVENT_NAME,
    MATCH_HEAD_PATTERN,
    MERGE_TOOL_SUFFIX,
    NO_CLEAN_OPEN_REVIEW_REASON_TEMPLATE,
    NO_CLEAN_REVIEW_REASON_TEMPLATE,
    NUMBER_FIELD,
    OPEN_RECEIPT_DIRECTORY_NAME,
    OPEN_RECEIPT_FILE_NAME_TEMPLATE,
    OPEN_HEAD_PATTERN,
    OPEN_RECEIPT_GLOB_TEMPLATE,
    OPTION_WITH_VALUE_PATTERN,
    ORIGIN_URL_PATTERN,
    OWNER_FIELD,
    PERMISSION_DECISION_REASON_KEY,
    PR_NUMBER_PATTERN,
    PR_URL_PATTERN,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE,
    RECEIPT_FILE_NAME_TEMPLATE,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_RULED_OUT_KEY,
    RECEIPT_RULINGS_KEY,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
    REPOSITORY_SEPARATOR,
    REVIEW_COMMAND_ENVIRONMENT_VARIABLE,
    RULINGS_LINK_PATTERN,
    REMOTE_BRANCH_PREFIX,
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


def open_receipt_path(owner: str, repo: str, head: str) -> Path:
    """Return where the review receipt for a head reviewed before its pull request opened lives.

    Args:
        owner: Repository owner.
        repo: Repository name.
        head: The commit the pass reviewed.

    Returns:
        The receipt file path.
    """
    return receipt_directory() / OPEN_RECEIPT_DIRECTORY_NAME / OPEN_RECEIPT_FILE_NAME_TEMPLATE.format(
        owner=owner.casefold(), repo=repo.casefold(), head=head.casefold()
    )


def has_clean_open_review(repo: str, head: str) -> bool:
    """Return whether a pass recorded before the pull request opened found zero findings at a head.

    The head may be a full or an abbreviated commit, matched against each
    recorded head by prefix. The owner is left out of the match, since a
    checkout whose origin still names a transferred repository's old owner
    opens against the new one::

        open receipt {head: abc1234..., findings: 0}, head abc1234 -> True
        open receipt {head: abc1234..., findings: 2}, head abc1234 -> False
        no open receipt for the repository                          -> False

    Args:
        repo: Repository name.
        head: The commit the open or merge names.

    Returns:
        True when a clean open receipt covers that head.
    """
    if not OPEN_HEAD_PATTERN.fullmatch(head):
        return False
    folder = receipt_directory() / OPEN_RECEIPT_DIRECTORY_NAME
    pattern = OPEN_RECEIPT_GLOB_TEMPLATE.format(repo=repo.casefold())
    for each_path in folder.glob(pattern):
        try:
            receipt = json.loads(each_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(receipt, dict):
            continue
        recorded_head = receipt.get(RECEIPT_HEAD_KEY)
        if (
            isinstance(recorded_head, str)
            and OPEN_HEAD_PATTERN.fullmatch(recorded_head)
            and _same_commit(recorded_head, head)
            and receipt.get(RECEIPT_FINDINGS_KEY) == 0
            and _is_count(receipt.get(RECEIPT_FINDINGS_KEY))
        ):
            return True
    return False


@dataclass(frozen=True)
class OpenRequest:
    """One pull request a tool call asks to open.

    Attributes:
        owner: Repository owner, or empty when it could not be read.
        repo: Repository name, or empty when it could not be read.
        head: The commit the pull request would open with, or None.
    """

    owner: str
    repo: str
    head: str | None

    @property
    def slug(self) -> str:
        """Return ``owner/repo``."""
        return f"{self.owner}/{self.repo}"


def open_request_from(all_payload_fields: dict[str, object]) -> OpenRequest | None:
    """Read the pull request open a PreToolUse payload asks for.

    ::

        mcp__github__create_pull_request {owner, repo, head}
        gh pr create --repo o/r --head branch
        python pull_request.py create --repo o/r --head branch

    A branch name resolves to its commit in the payload's working folder,
    first as a local branch and then as ``origin/<branch>``. A call with no
    head opens the checked-out commit, and a call with no repository opens
    against the ``origin`` remote.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The open request, or None when the call opens no pull request.
    """
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    working_folder = all_payload_fields.get(CWD_FIELD)
    folder = working_folder if isinstance(working_folder, str) and working_folder else None
    if tool_name.endswith(CREATE_TOOL_SUFFIX):
        branch = tool_input.get(HEAD_BRANCH_FIELD)
        return OpenRequest(
            owner=str(tool_input.get(OWNER_FIELD, "")),
            repo=str(tool_input.get(REPO_FIELD, "")),
            head=_branch_commit(branch, folder) if isinstance(branch, str) and branch else None,
        )
    command = tool_input.get("command")
    if tool_name not in ALL_SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    create_match = GH_PR_CREATE_PATTERN.search(command) or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(
        command
    )
    if not create_match:
        return None
    rest = create_match["rest"]
    repo_match = REPO_OPTION_PATTERN.search(rest)
    owner, repo = (
        (repo_match["owner"], repo_match["repo"]) if repo_match else _origin_repository(folder)
    )
    head_match = HEAD_OPTION_PATTERN.search(rest)
    branch = head_match["head"] if head_match else CURRENT_HEAD_REFERENCE
    return OpenRequest(owner=owner, repo=repo, head=_branch_commit(branch, folder))


def _run_git(all_arguments: list[str], folder: str | None) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *all_arguments],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _branch_commit(branch: str, folder: str | None) -> str | None:
    branch_name = branch.split(":", 1)[-1]
    all_references = (
        (branch_name,)
        if branch_name == CURRENT_HEAD_REFERENCE
        else (REMOTE_BRANCH_PREFIX + branch_name, branch_name)
    )
    for each_reference in all_references:
        commit = _run_git(["rev-parse", "--verify", "--quiet", f"{each_reference}^{{commit}}"], folder)
        if commit:
            return commit
    return None


def _origin_repository(folder: str | None) -> tuple[str, str]:
    origin_url = _run_git(["remote", "get-url", "origin"], folder)
    origin_match = ORIGIN_URL_PATTERN.search(origin_url) if origin_url else None
    if not origin_match:
        return "", ""
    return origin_match["owner"], origin_match["repo"]


def open_deny_reason(request: OpenRequest) -> str | None:
    """Return why a pull request open must wait for a clean review, or None to allow it.

    Args:
        request: The open the tool call asks for.

    Returns:
        The deny reason, or None when the open may run.
    """
    if not request.owner or not request.repo or not request.head:
        return UNKNOWN_OPEN_TARGET_REASON
    if _is_exempt(request.slug):
        return None
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


def _receipt_head(receipt: dict[str, object] | None) -> str | None:
    head = receipt.get(RECEIPT_HEAD_KEY) if receipt else None
    return head if isinstance(head, str) and head else None


def _clean_head(request: MergeRequest, receipt: dict[str, object] | None) -> str | None:
    if receipt is None or request.number is None:
        return None
    if not is_clean_receipt(receipt, request.owner, request.repo, request.number):
        return None
    return _receipt_head(receipt)


def is_clean_receipt(
    all_receipt_fields: dict[str, object], owner: str, repo: str, number: int
) -> bool:
    """Return whether a recorded pass lets the merge through.

    A pass is clean when it reported zero findings, or when every finding it
    reported is ruled out and the receipt links the rulings comment posted on
    this same pull request::

        findings 0                                                -> clean
        findings 2, ruled out 2, .../acme/tools/pull/12#issuecomment-9 -> clean
        findings 2, ruled out 2, .../acme/other/pull/12#issuecomment-9 -> not clean

    Args:
        all_receipt_fields: The parsed receipt of one review pass.
        owner: Owner of the pull request the merge targets.
        repo: Repository of the pull request the merge targets.
        number: Number of the pull request the merge targets.

    Returns:
        True when the pass counts as clean.
    """
    finding_count = all_receipt_fields.get(RECEIPT_FINDINGS_KEY)
    if not _is_count(finding_count):
        return False
    return finding_count == 0 or _rules_out_every_finding(
        all_receipt_fields, finding_count, owner, repo, number
    )


def _is_count(candidate: object) -> bool:
    return isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0


def _rules_out_every_finding(
    all_receipt_fields: dict[str, object], finding_count: object, owner: str, repo: str, number: int
) -> bool:
    ruled_out_count = all_receipt_fields.get(RECEIPT_RULED_OUT_KEY)
    return (
        _is_count(ruled_out_count)
        and ruled_out_count == finding_count
        and _links_rulings_on(all_receipt_fields.get(RECEIPT_RULINGS_KEY), owner, repo, number)
    )


def _links_rulings_on(rulings: object, owner: str, repo: str, number: int) -> bool:
    rulings_match = RULINGS_LINK_PATTERN.fullmatch(rulings) if isinstance(rulings, str) else None
    return (
        rulings_match is not None
        and rulings_match["owner"].casefold() == owner.casefold()
        and rulings_match["repo"].casefold() == repo.casefold()
        and int(rulings_match["number"]) == number
    )


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
    if _is_exempt(request.slug):
        return None
    numbered_receipt = _numbered_receipt(request)
    numbered_head = _receipt_head(numbered_receipt)
    pass_on_pinned_head = (
        numbered_head is not None
        and request.pinned_head is not None
        and _same_commit(numbered_head, request.pinned_head)
    )
    if (
        request.pinned_head
        and not pass_on_pinned_head
        and has_clean_open_review(request.repo, request.pinned_head)
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
    if not _same_commit(clean_head, request.pinned_head):
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
    open_request = open_request_from(all_payload_fields)
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
