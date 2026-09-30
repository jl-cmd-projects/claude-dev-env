"""Refusal behavior for native review evidence whose success format is unknown."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import codex_review_observer as observer
import review_closure_github
from pr_verification.github_parsing import GitHubError

HEAD = "a" * 40
NEXT_HEAD = "b" * 40
CANDIDATE = observer.Candidate("owner/repository", 7, HEAD)


def observe(
    all_pages: list[object], after_head: str = HEAD
) -> observer.ReviewObservation:
    all_reads: list[object] = [
        {"number": 7, "head": {"sha": HEAD}},
        *all_pages,
        {"number": 7, "head": {"sha": after_head}},
    ]

    def read(url: str) -> object:
        if "/issues/7/comments?" in url:
            return []
        assert url.startswith("https://api.github.com/repos/owner/repository/pulls/7")
        return all_reads.pop(0)

    return observer.observe_codex_review(CANDIDATE, read)


@pytest.mark.parametrize(
    "body",
    [
        "No findings. Review completed successfully.",
        "Fixed in the next push.",
        "Review resolved.",
        "Codex cloud task completed.",
        "You've reached your Codex code review usage limits.",
    ],
)
def test_body_text_never_authorizes_merge(body: str) -> None:
    review = {"id": 1, "commit_id": HEAD, "state": "APPROVED", "body": body}
    observed = observe([[review]])
    assert observed.reason is observer.HoldReason.NATIVE_FORMAT_UNVERIFIED
    assert observed.evidence_ids == (1,)


def test_missing_review_holds() -> None:
    assert observe([[]]).reason is observer.HoldReason.MISSING_REVIEW


def test_stale_completion_holds() -> None:
    review = {"id": 1, "commit_id": NEXT_HEAD, "state": "APPROVED"}
    assert observe([[review]]).reason is observer.HoldReason.STALE_REVIEW


def test_head_movement_invalidates_observation() -> None:
    review = {"id": 1, "commit_id": HEAD, "state": "APPROVED"}
    assert observe([[review]], NEXT_HEAD).reason is observer.HoldReason.HEAD_CHANGED


@pytest.mark.parametrize(
    "state", ["PENDING", "DISMISSED", "FAILED", "CANCELLED", "SKIPPED"]
)
def test_unsuccessful_state_holds(state: str) -> None:
    review = {"id": 1, "commit_id": HEAD, "state": state}
    assert observe([[review]]).reason is observer.HoldReason.NATIVE_FORMAT_UNVERIFIED


def test_identical_duplicates_are_idempotent() -> None:
    review = {"id": 1, "commit_id": HEAD, "body": "No findings"}
    assert observe([[review, review]]).evidence_ids == (1,)


def test_conflicting_duplicate_cannot_pass() -> None:
    first = {"id": 1, "commit_id": HEAD, "body": "No findings"}
    later = {**first, "body": "A finding remains"}
    assert observe([[first, later]]).reason is observer.HoldReason.CONFLICTING_EVIDENCE


def test_delayed_success_cannot_override_newer_failure() -> None:
    failed = {"id": 2, "commit_id": HEAD, "state": "FAILED"}
    delayed = {"id": 1, "commit_id": HEAD, "state": "APPROVED"}
    assert (
        observe([[failed, delayed]]).reason
        is observer.HoldReason.NATIVE_FORMAT_UNVERIFIED
    )


@pytest.mark.parametrize(
    "failure", [TimeoutError(), GitHubError("quota unavailable"), OSError()]
)
def test_transport_failure_holds(failure: Exception) -> None:
    def read(url: str) -> object:
        raise failure

    observed = observer.observe_codex_review(CANDIDATE, read)
    assert observed.reason in (
        observer.HoldReason.READ_TIMEOUT,
        observer.HoldReason.READ_UNAVAILABLE,
    )


@pytest.mark.parametrize("page", [None, {}, [None], [{"id": "1"}]])
def test_malformed_review_collection_holds(page: object) -> None:
    assert observe([page]).reason is observer.HoldReason.INCOMPLETE_READ


def test_incomplete_pagination_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observer, "MAX_PAGES", 1)
    all_reviews = [{"id": each_id + 1, "commit_id": HEAD} for each_id in range(100)]
    assert observe([all_reviews]).reason is observer.HoldReason.INCOMPLETE_READ


@pytest.mark.parametrize("head", ["abc123", "A" * 40, "a" * 39])
def test_candidate_requires_full_head(head: str) -> None:
    with pytest.raises(ValueError):
        observer.Candidate("owner/repository", 7, head)


def test_wrong_pull_request_is_a_hold() -> None:
    def read(url: str) -> object:
        return {"number": 8, "head": {"sha": HEAD}}

    assert (
        observer.observe_codex_review(CANDIDATE, read).reason
        is observer.HoldReason.HEAD_CHANGED
    )


def test_cli_returns_nonzero_with_plausible_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(observer, "github_token", lambda: "test-token")
    all_reads = iter(
        [
            {"number": 7, "head": {"sha": HEAD}},
            [{"id": 1, "commit_id": HEAD, "state": "APPROVED"}],
            {"number": 7, "head": {"sha": HEAD}},
        ]
    )
    monkeypatch.setattr(observer, "request_json", lambda *arguments: next(all_reads))
    assert observer.main(["owner/repository", "7", HEAD]) == 1
    assert '"admission": "hold"' in capsys.readouterr().out


def test_parent_verified_submitted_findings_hold() -> None:
    fixture_path = Path(__file__).parent / "fixtures/codex-submitted-findings.json"
    captured = json.loads(fixture_path.read_text(encoding="utf-8"))
    review = captured["review"]
    candidate = observer.Candidate(
        captured["repository"], captured["pull_request"], review["commit_id"]
    )
    all_reads = iter(
        [
            {"number": candidate.pull_request, "head": {"sha": candidate.head_sha}},
            [review],
            {"number": candidate.pull_request, "head": {"sha": candidate.head_sha}},
        ]
    )
    observed = observer.observe_codex_review(candidate, lambda url: next(all_reads))
    assert observed.reason is observer.HoldReason.REVIEW_FINDINGS
    assert observed.evidence_ids == (5322799208,)


def test_native_pilot_heading_preserves_findings_hold() -> None:
    captured = json.loads(
        (Path(__file__).parent / "fixtures/codex-pilot-findings.json").read_text(
            encoding="utf-8-sig"
        )
    )
    review = captured["review"]
    candidate = observer.Candidate(
        captured["repository"], captured["pull_request"], review["commit_id"]
    )
    all_reads = iter(
        [
            {"number": candidate.pull_request, "head": {"sha": candidate.head_sha}},
            [review],
            {"number": candidate.pull_request, "head": {"sha": candidate.head_sha}},
        ]
    )
    observed = observer.observe_codex_review(candidate, lambda url: next(all_reads))
    assert observed.reason is observer.HoldReason.REVIEW_FINDINGS
    assert observed.evidence_ids == (5360553725,)


def test_cli_production_transport_preserves_timeout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def timed_out(*args: object, **kwargs: object) -> object:
        raise TimeoutError("socket read timed out")

    monkeypatch.setattr(observer, "github_token", lambda: "test-token")
    monkeypatch.setattr(review_closure_github.urllib.request, "urlopen", timed_out)
    assert observer.main(["owner/repository", "7", HEAD]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "read_timeout"


def test_findings_text_from_wrong_actor_stays_unsupported() -> None:
    review = {
        "id": 1,
        "commit_id": HEAD,
        "state": "COMMENTED",
        "submitted_at": "2026-09-25T21:15:07Z",
        "user": {"login": "unrelated-reviewer"},
        "body": observer.CODEX_FINDINGS_PREFIX,
    }
    assert observe([[review]]).reason is observer.HoldReason.NATIVE_FORMAT_UNVERIFIED


@pytest.mark.parametrize("actor", [observer.CODEX_REVIEWER_LOGIN, "other-user"])
@pytest.mark.parametrize(
    "fixture_name", ["codex-quota-comment.json", "codex-quota-credits-comment.json"]
)
def test_authentic_quota_comment_is_diagnostic_only(
    actor: str, fixture_name: str
) -> None:
    comment = json.loads(
        (Path(__file__).parent / "fixtures" / fixture_name).read_text(
            encoding="utf-8-sig"
        )
    )
    comment["user"]["login"] = actor

    def read(url: str) -> object:
        if "/reviews?" in url:
            return []
        if "/comments?" in url:
            return [comment]
        return {"number": 7, "head": {"sha": HEAD}}

    observed = observer.observe_codex_review(CANDIDATE, read)
    assert observed.reason is (
        observer.HoldReason.QUOTA_NOTICE
        if actor == observer.CODEX_REVIEWER_LOGIN
        else observer.HoldReason.MISSING_REVIEW
    )
    assert observed.evidence_ids == ()
    assert observed.quota_notice_ids == (
        (comment["id"],) if actor == observer.CODEX_REVIEWER_LOGIN else ()
    )


@pytest.mark.parametrize(
    "response,reason",
    [
        ({}, observer.HoldReason.INCOMPLETE_READ),
        ([None], observer.HoldReason.INCOMPLETE_READ),
        (TimeoutError(), observer.HoldReason.READ_TIMEOUT),
    ],
)
def test_quota_comment_read_failure_holds(
    response: object, reason: observer.HoldReason
) -> None:
    def read(url: str) -> object:
        if "/reviews?" in url:
            return []
        if "/comments?" in url:
            if isinstance(response, Exception):
                raise response
            return response
        return {"number": 7, "head": {"sha": HEAD}}

    assert observer.observe_codex_review(CANDIDATE, read).reason is reason
