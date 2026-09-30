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
from urllib.error import URLError

from dev_env_scripts_constants.codex_review_observer_constants import (
    CODEX_FINDINGS_HEADING,
    CODEX_FINDINGS_PREFIX,
    CODEX_QUOTA_PREFIX,
    CODEX_REVIEWER_LOGIN,
    COMMENTS_URL,
    COMMIT_PATTERN,
    HOLD_EXIT_CODE,
    MAX_PAGES,
    PAGE_SIZE,
    PULL_URL,
    REPOSITORY_PATTERN,
    REVIEWS_SUFFIX,
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


def _is_submitted_codex_findings(all_review: Mapping[str, object]) -> bool:
    author = all_review.get("user")
    body = all_review.get("body")
    submitted_at = all_review.get("submitted_at")
    if not (
        isinstance(author, Mapping)
        and author.get("login") == CODEX_REVIEWER_LOGIN
        and all_review.get("state") == "COMMENTED"
        and isinstance(body, str)
        and body.lstrip().startswith((CODEX_FINDINGS_PREFIX, CODEX_FINDINGS_HEADING))
        and isinstance(submitted_at, str)
    ):
        return False
    try:
        return datetime.fromisoformat(submitted_at).tzinfo is not None
    except ValueError:
        return False


class _EvidenceReadRunFatal(Exception):
    def __init__(self, reason: HoldReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _merge_page(all_records: dict[int, Mapping[str, object]], all_page: object) -> int:
    if not isinstance(all_page, list):
        raise _EvidenceReadRunFatal(HoldReason.INCOMPLETE_READ)
    for each_record in all_page:
        if not isinstance(each_record, Mapping):
            raise _EvidenceReadRunFatal(HoldReason.INCOMPLETE_READ)
        record_id = each_record.get("id")
        if type(record_id) is not int or record_id <= 0:
            raise _EvidenceReadRunFatal(HoldReason.INCOMPLETE_READ)
        if record_id in all_records and all_records[record_id] != each_record:
            raise _EvidenceReadRunFatal(HoldReason.CONFLICTING_EVIDENCE)
        all_records[record_id] = each_record
    return len(all_page)


def _read_collection(url: str, read: GitHubRead) -> dict[int, Mapping[str, object]]:
    all_records: dict[int, Mapping[str, object]] = {}
    for each_page in range(1, MAX_PAGES + 1):
        count = _merge_page(
            all_records, read(f"{url}?per_page={PAGE_SIZE}&page={each_page}")
        )
        if count < PAGE_SIZE:
            return all_records
    raise _EvidenceReadRunFatal(HoldReason.INCOMPLETE_READ)


def _quota_notice_ids(
    all_comments: Mapping[int, Mapping[str, object]],
) -> tuple[int, ...]:
    all_ids: list[int] = []
    for each_id, each_comment in all_comments.items():
        author = each_comment.get("user")
        body = each_comment.get("body")
        if (
            isinstance(author, Mapping)
            and author.get("login") == CODEX_REVIEWER_LOGIN
            and isinstance(body, str)
            and body.startswith(CODEX_QUOTA_PREFIX)
        ):
            all_ids.append(each_id)
    return tuple(sorted(all_ids))


def _review_observation(
    candidate: Candidate, all_reviews: Mapping[int, Mapping[str, object]]
) -> ReviewObservation:
    all_current = {
        each_id: each_review
        for each_id, each_review in all_reviews.items()
        if each_review.get("commit_id") == candidate.head_sha
    }
    reason = HoldReason.MISSING_REVIEW
    if all_reviews:
        reason = HoldReason.STALE_REVIEW
    if all_current:
        reason = HoldReason.NATIVE_FORMAT_UNVERIFIED
    if any(
        _is_submitted_codex_findings(each_review)
        for each_review in all_current.values()
    ):
        reason = HoldReason.REVIEW_FINDINGS
    return ReviewObservation(candidate, reason, tuple(sorted(all_current)))


def _stable_observation(
    candidate: Candidate, read: GitHubRead, pull_url: str
) -> ReviewObservation:
    all_reviews = _read_collection(pull_url + REVIEWS_SUFFIX, read)
    observation = _review_observation(candidate, all_reviews)
    if observation.reason in (HoldReason.MISSING_REVIEW, HoldReason.STALE_REVIEW):
        comments_url = COMMENTS_URL.format(
            repository=candidate.repository, number=candidate.pull_request
        )
        all_quota_ids = _quota_notice_ids(_read_collection(comments_url, read))
        if all_quota_ids:
            observation = ReviewObservation(
                candidate, HoldReason.QUOTA_NOTICE, (), all_quota_ids
            )
    return observation


def _transport_failure_reason(failure: BaseException) -> HoldReason:
    cause = failure.__cause__
    if isinstance(failure, TimeoutError) or isinstance(cause, TimeoutError):
        return HoldReason.READ_TIMEOUT
    if isinstance(cause, URLError) and isinstance(cause.reason, TimeoutError):
        return HoldReason.READ_TIMEOUT
    return HoldReason.READ_UNAVAILABLE


def observe_codex_review(candidate: Candidate, read: GitHubRead) -> ReviewObservation:
    """Read evidence for a stable full head and return its admission hold.

    Args:
        candidate: The repository, pull request, and requested full head.
        read: Authenticated read-only JSON transport.

    Returns:
        The observed hold and evidence identifiers.
    """
    pull_url = PULL_URL.format(
        repository=candidate.repository, number=candidate.pull_request
    )
    observation = ReviewObservation(candidate, HoldReason.MISSING_REVIEW)
    try:
        if not _matches_candidate(read(pull_url), candidate):
            return ReviewObservation(candidate, HoldReason.HEAD_CHANGED)
        try:
            observation = _stable_observation(candidate, read, pull_url)
        except _EvidenceReadRunFatal as failure:
            observation = ReviewObservation(candidate, failure.reason)
        if not _matches_candidate(read(pull_url), candidate):
            return ReviewObservation(candidate, HoldReason.HEAD_CHANGED)
    except TimeoutError:
        return ReviewObservation(candidate, HoldReason.READ_TIMEOUT)
    except (GitHubError, OSError) as failure:
        return ReviewObservation(candidate, _transport_failure_reason(failure))
    return observation


def _observation_document(observation: ReviewObservation) -> dict[str, object]:
    candidate = observation.candidate
    return {
        "repository": candidate.repository,
        "pull_request": candidate.pull_request,
        "head_sha": candidate.head_sha,
        "admission": "hold",
        "reason": observation.reason.value,
        "evidence_ids": observation.evidence_ids,
        "quota_notice_ids": observation.quota_notice_ids,
    }


def _parse_candidate(all_arguments: Sequence[str]) -> Candidate:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("pull_request", type=int)
    parser.add_argument("head_sha")
    parsed = parser.parse_args(all_arguments)
    return Candidate(parsed.repository, parsed.pull_request, parsed.head_sha)


def main(all_arguments: Sequence[str]) -> int:
    """Print a read-only observation and return nonzero for every hold.

    Args:
        all_arguments: Command arguments without the executable name.

    Returns:
        One for a hold, or two when the read is unavailable.
    """
    try:
        candidate = _parse_candidate(all_arguments)
        token = github_token()
    except (ValueError, GitHubError) as failure:
        print(str(failure), file=sys.stderr)
        return UNAVAILABLE_EXIT_CODE

    def read(url: str) -> object:
        return request_json("GET", url, token, None)

    observation = observe_codex_review(candidate, read)
    print(json.dumps(_observation_document(observation)))
    return (
        UNAVAILABLE_EXIT_CODE
        if observation.reason in (HoldReason.READ_TIMEOUT, HoldReason.READ_UNAVAILABLE)
        else HOLD_EXIT_CODE
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
