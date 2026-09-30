"""Observe candidate reviews without granting admission to a merge queue.

Native completion representation and reviewer identity remain unverified.
Every observation holds admission, including plausible success records.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from dev_env_scripts_constants.codex_review_observer_constants import (
    CODEX_FINDINGS_PREFIX,
    CODEX_REVIEWER_LOGIN,
    COMMIT_PATTERN,
    GITHUB_API_ROOT,
    HOLD_EXIT_CODE,
    MAX_PAGES,
    PAGE_SIZE,
    REPOSITORY_PATTERN,
    UNAVAILABLE_EXIT_CODE,
)
from pr_verification.github_parsing import GitHubError
from review_closure_github import github_token, request_json

GitHubRead = Callable[[str], object]


class HoldReason(str, Enum):
    MISSING_REVIEW = "missing_review"
    STALE_REVIEW = "stale_review"
    HEAD_CHANGED = "head_changed"
    NATIVE_FORMAT_UNVERIFIED = "native_format_unverified"
    READ_UNAVAILABLE = "read_unavailable"
    READ_TIMEOUT = "read_timeout"
    INCOMPLETE_READ = "incomplete_read"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    REVIEW_FINDINGS = "review_findings"
    QUOTA_NOTICE = "quota_notice"


@dataclass(frozen=True)
class Candidate:
    repository: str
    pull_request: int
    head_sha: str

    def __post_init__(self) -> None:
        if (
            re.fullmatch(REPOSITORY_PATTERN, self.repository) is None
            or type(self.pull_request) is not int
            or self.pull_request <= 0
            or re.fullmatch(COMMIT_PATTERN, self.head_sha) is None
        ):
            raise ValueError("A repository, pull request, and full head are required.")


@dataclass(frozen=True)
class ReviewObservation:
    candidate: Candidate
    reason: HoldReason
    evidence_ids: tuple[int, ...] = ()
    quota_notice_ids: tuple[int, ...] = ()


def _matches_candidate(document: object, candidate: Candidate) -> bool:
    if not isinstance(document, Mapping):
        return False
    head = document.get("head")
    return (
        document.get("number") == candidate.pull_request
        and isinstance(head, Mapping)
        and head.get("sha") == candidate.head_sha
    )


def _is_submitted_codex_findings(review: Mapping[str, object]) -> bool:
    author = review.get("user")
    body = review.get("body")
    submitted_at = review.get("submitted_at")
    if not (
        isinstance(author, Mapping)
        and author.get("login") == CODEX_REVIEWER_LOGIN
        and review.get("state") == "COMMENTED"
        and isinstance(body, str)
        and body.startswith(CODEX_FINDINGS_PREFIX)
        and isinstance(submitted_at, str)
    ):
        return False
    try:
        return datetime.fromisoformat(submitted_at).tzinfo is not None
    except ValueError:
        return False


def observe_codex_review(candidate: Candidate, read: GitHubRead) -> ReviewObservation:
    """Read a stable candidate and return a hold for unsupported native evidence.

    Args:
        candidate: The repository, pull request, and requested full head.
        read: An authenticated read-only transport returning decoded JSON.

    Returns:
        A hold reason and the current-head review identifiers inspected.
    """
    pull_url = (
        f"{GITHUB_API_ROOT}/repos/{candidate.repository}/pulls/{candidate.pull_request}"
    )
    reason = HoldReason.MISSING_REVIEW
    review_by_id: dict[int, Mapping[str, object]] = {}
    all_current_ids: set[int] = set()
    has_codex_findings = False
    quota_ids: set[int] = set()
    try:
        if not _matches_candidate(read(pull_url), candidate):
            return ReviewObservation(candidate, HoldReason.HEAD_CHANGED)
        for each_page in range(1, MAX_PAGES + 1):
            all_reviews = read(
                f"{pull_url}/reviews?per_page={PAGE_SIZE}&page={each_page}"
            )
            if not isinstance(all_reviews, list):
                reason = HoldReason.INCOMPLETE_READ
                break
            for each_review in all_reviews:
                if not isinstance(each_review, Mapping):
                    reason = HoldReason.INCOMPLETE_READ
                    break
                review_id = each_review.get("id")
                commit_id = each_review.get("commit_id")
                if type(review_id) is not int or review_id <= 0:
                    reason = HoldReason.INCOMPLETE_READ
                    break
                if review_id in review_by_id and review_by_id[review_id] != each_review:
                    reason = HoldReason.CONFLICTING_EVIDENCE
                    break
                review_by_id[review_id] = each_review
                if commit_id == candidate.head_sha:
                    all_current_ids.add(review_id)
                    has_codex_findings = (
                        has_codex_findings or _is_submitted_codex_findings(each_review)
                    )
            if reason in (HoldReason.INCOMPLETE_READ, HoldReason.CONFLICTING_EVIDENCE):
                break
            if len(all_reviews) < PAGE_SIZE:
                reason = (
                    HoldReason.REVIEW_FINDINGS
                    if has_codex_findings
                    else HoldReason.NATIVE_FORMAT_UNVERIFIED
                    if all_current_ids
                    else HoldReason.STALE_REVIEW
                    if review_by_id
                    else HoldReason.MISSING_REVIEW
                )
                break
        else:
            reason = HoldReason.INCOMPLETE_READ
        if reason is HoldReason.MISSING_REVIEW:
            comments_url = (
                f"{GITHUB_API_ROOT}/repos/{candidate.repository}/issues/"
                f"{candidate.pull_request}/comments"
            )
            seen_comments: dict[int, Mapping[str, object]] = {}
            for page in range(1, MAX_PAGES + 1):
                comments = read(f"{comments_url}?per_page={PAGE_SIZE}&page={page}")
                if not isinstance(comments, list):
                    reason = HoldReason.INCOMPLETE_READ
                    break
                for comment in comments:
                    if not isinstance(comment, Mapping):
                        reason = HoldReason.INCOMPLETE_READ
                        break
                    comment_id = comment.get("id")
                    if type(comment_id) is not int or comment_id <= 0:
                        reason = HoldReason.INCOMPLETE_READ
                        break
                    if (
                        comment_id in seen_comments
                        and seen_comments[comment_id] != comment
                    ):
                        reason = HoldReason.CONFLICTING_EVIDENCE
                        break
                    seen_comments[comment_id] = comment
                if reason in (
                    HoldReason.INCOMPLETE_READ,
                    HoldReason.CONFLICTING_EVIDENCE,
                ):
                    break
                if len(comments) < PAGE_SIZE:
                    for comment in seen_comments.values():
                        author = comment.get("user")
                        body = comment.get("body")
                        if (
                            isinstance(author, Mapping)
                            and author.get("login") == CODEX_REVIEWER_LOGIN
                            and isinstance(body, str)
                            and body.startswith(
                                "You have reached your Codex usage limits for code reviews."
                            )
                        ):
                            reason = HoldReason.QUOTA_NOTICE
                            quota_ids.add(comment["id"])
                    break
            else:
                reason = HoldReason.INCOMPLETE_READ
        if not _matches_candidate(read(pull_url), candidate):
            reason = HoldReason.HEAD_CHANGED
    except TimeoutError:
        reason = HoldReason.READ_TIMEOUT
    except (GitHubError, OSError):
        reason = HoldReason.READ_UNAVAILABLE
    return ReviewObservation(
        candidate, reason, tuple(sorted(all_current_ids)), tuple(sorted(quota_ids))
    )


def main(all_arguments: Sequence[str]) -> int:
    """Print a read-only observation and return nonzero for every hold.

    Args:
        all_arguments: Command arguments without the executable name.

    Returns:
        One for a hold, or two when the read is unavailable.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("pull_request", type=int)
    parser.add_argument("head_sha")
    parsed = parser.parse_args(all_arguments)
    try:
        candidate = Candidate(parsed.repository, parsed.pull_request, parsed.head_sha)
        token = github_token()
    except (ValueError, GitHubError) as failure:
        print(str(failure), file=sys.stderr)
        return UNAVAILABLE_EXIT_CODE

    def read(url: str) -> object:
        return request_json("GET", url, token, None)

    observation = observe_codex_review(candidate, read)
    print(
        json.dumps(
            {
                "repository": candidate.repository,
                "pull_request": candidate.pull_request,
                "head_sha": candidate.head_sha,
                "admission": "hold",
                "reason": observation.reason.value,
                "evidence_ids": observation.evidence_ids,
                "quota_notice_ids": observation.quota_notice_ids,
            }
        )
    )
    return (
        UNAVAILABLE_EXIT_CODE
        if observation.reason in (HoldReason.READ_TIMEOUT, HoldReason.READ_UNAVAILABLE)
        else HOLD_EXIT_CODE
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
