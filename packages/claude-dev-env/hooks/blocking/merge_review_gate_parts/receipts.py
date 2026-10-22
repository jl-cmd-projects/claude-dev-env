"""Read the review receipts ``scripts/merge_review_receipt.py`` writes.

A numbered receipt covers one pull request. An open receipt covers one head
reviewed before its pull request opened.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_RECEIPT_DIRECTORY_SEGMENTS,
    OPEN_HEAD_PATTERN,
    OPEN_RECEIPT_DIRECTORY_NAME,
    OPEN_RECEIPT_FILE_NAME_TEMPLATE,
    OPEN_RECEIPT_GLOB_TEMPLATE,
    OPEN_RECEIPT_HEAD_PATTERN,
    RECEIPT_DIRECTORY_ENVIRONMENT_VARIABLE,
    RECEIPT_FILE_NAME_TEMPLATE,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_RULED_OUT_KEY,
    RECEIPT_RULINGS_KEY,
    RULINGS_LINK_PATTERN,
)


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
    return (
        receipt_directory()
        / OPEN_RECEIPT_DIRECTORY_NAME
        / OPEN_RECEIPT_FILE_NAME_TEMPLATE.format(
            owner=owner.casefold(), repo=repo.casefold(), head=head.casefold()
        )
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
    return any(_is_clean_open_receipt(each_path, head) for each_path in folder.glob(pattern))


def _is_clean_open_receipt(path: Path, head: str) -> bool:
    try:
        all_receipt_fields = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(all_receipt_fields, dict):
        return False
    recorded_head = all_receipt_fields.get(RECEIPT_HEAD_KEY)
    return (
        isinstance(recorded_head, str)
        and OPEN_RECEIPT_HEAD_PATTERN.fullmatch(recorded_head) is not None
        and same_commit(recorded_head, head)
        and _is_count(all_receipt_fields.get(RECEIPT_FINDINGS_KEY))
        and all_receipt_fields.get(RECEIPT_FINDINGS_KEY) == 0
    )


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


def same_commit(first: str, second: str) -> bool:
    """Return whether two commit names match, one being a prefix of the other.

    Args:
        first: A full or abbreviated commit.
        second: A full or abbreviated commit.

    Returns:
        True when the shorter name starts the longer one.
    """
    shorter, longer = sorted((first.casefold(), second.casefold()), key=len)
    return longer.startswith(shorter)


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
