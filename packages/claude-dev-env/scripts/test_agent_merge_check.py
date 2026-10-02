"""Tests for the agent merge-readiness check."""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

import pytest

_SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(_SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIRECTORY))

import agent_merge_check
from dev_env_scripts_constants.agent_merge_check_constants import (
    BEHIND_HOLD_REASON,
    BEHIND_MERGE_QUEUE_HOLD_TEMPLATE,
    BLOCKED_HOLD_REASON,
    DIRTY_HOLD_REASON,
    DRAFT_HOLD_REASON,
    HOLD_VERDICT_LABEL,
    MERGE_VERDICT_LABEL,
    SETTLE_ATTEMPT_COUNT,
    UNSTABLE_HOLD_REASON,
)

CLEAN_PULL_REQUEST = {
    "number": 1442,
    "draft": False,
    "mergeable_state": "clean",
    "head": {"sha": "ab845eb6945650055ebe852312a9057b9f067d6a"},
}


def _pull_request(**all_overrides: object) -> dict[str, object]:
    return {**CLEAN_PULL_REQUEST, **all_overrides}


def test_clean_pull_request_with_no_open_thread_may_merge() -> None:
    assert agent_merge_check.hold_reason(CLEAN_PULL_REQUEST, 0) is None


@pytest.mark.parametrize(
    ("all_overrides", "expected_reason"),
    [
        ({"draft": True}, DRAFT_HOLD_REASON),
        ({"mergeable_state": "behind"}, BEHIND_HOLD_REASON),
        ({"mergeable_state": "dirty"}, DIRTY_HOLD_REASON),
        ({"mergeable_state": "blocked"}, BLOCKED_HOLD_REASON),
        ({"mergeable_state": "unstable"}, UNSTABLE_HOLD_REASON),
    ],
)
def test_each_unready_state_holds_with_its_own_reason(
    all_overrides: dict[str, object],
    expected_reason: str,
) -> None:
    assert (
        agent_merge_check.hold_reason(_pull_request(**all_overrides), 0)
        == expected_reason
    )


def test_a_draft_holds_even_when_its_merge_state_is_clean() -> None:
    assert (
        agent_merge_check.hold_reason(_pull_request(draft=True), 0) == DRAFT_HOLD_REASON
    )


def test_an_unreported_merge_state_holds_and_names_what_github_said() -> None:
    reason = agent_merge_check.hold_reason(_pull_request(mergeable_state="unknown"), 0)
    assert reason is not None
    assert "unknown" in reason


def test_an_open_review_thread_holds_a_green_pull_request() -> None:
    reason = agent_merge_check.hold_reason(CLEAN_PULL_REQUEST, 2)
    assert reason is not None
    assert "2" in reason


def test_an_open_thread_count_reaches_the_verdict_line() -> None:
    reason = agent_merge_check.hold_reason(CLEAN_PULL_REQUEST, 1)
    line = agent_merge_check.verdict_line(
        "jl-cmd/claude-dev-env", CLEAN_PULL_REQUEST, reason
    )
    assert line.startswith(HOLD_VERDICT_LABEL)
    assert "jl-cmd/claude-dev-env#1442" in line


def test_the_ready_verdict_line_names_the_repository_and_head() -> None:
    line = agent_merge_check.verdict_line(
        "jl-cmd/claude-dev-env", CLEAN_PULL_REQUEST, None
    )
    assert line.startswith(MERGE_VERDICT_LABEL)
    assert "jl-cmd/claude-dev-env#1442" in line
    assert "ab845eb" in line


def test_a_resolved_thread_and_an_outdated_thread_hold_nothing_back() -> None:
    all_thread_records = [
        {"isResolved": True, "isOutdated": False},
        {"isResolved": False, "isOutdated": True},
    ]
    assert agent_merge_check.count_unresolved_threads(all_thread_records) == 0


def test_an_unresolved_current_thread_counts() -> None:
    all_thread_records = [
        {"isResolved": False, "isOutdated": False},
        {"isResolved": True, "isOutdated": False},
        {"isResolved": False, "isOutdated": False},
    ]
    assert agent_merge_check.count_unresolved_threads(all_thread_records) == 2


def test_a_thread_record_of_another_shape_counts_as_nothing() -> None:
    assert agent_merge_check.count_unresolved_threads(["", None]) == 0


def test_read_pull_request_returns_the_fields_the_api_answered_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        lambda url, token, all_payload_fields: CLEAN_PULL_REQUEST,
    )
    assert (
        agent_merge_check.read_pull_request("jl-cmd/claude-dev-env", 1442, "token")
        == CLEAN_PULL_REQUEST
    )


def test_read_pull_request_rejects_an_answer_of_another_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        lambda url, token, all_payload_fields: ["not a pull request"],
    )
    with pytest.raises(agent_merge_check.MergeCheckError):
        agent_merge_check.read_pull_request("jl-cmd/claude-dev-env", 1442, "token")


def test_read_unresolved_thread_count_reads_the_rest_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        lambda url, token, all_payload_fields: [
            {"isResolved": False, "isOutdated": False},
            {"isResolved": True, "isOutdated": False},
        ],
    )
    assert (
        agent_merge_check.read_unresolved_thread_count(
            "jl-cmd/claude-dev-env", 1442, "token"
        )
        == 1
    )


def test_read_unresolved_thread_count_falls_back_to_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _answer(
        url: str,
        token: str,
        all_payload_fields: object,
    ) -> object:
        if all_payload_fields is None:
            raise agent_merge_check.MergeCheckError("HTTP Error 403: Forbidden")
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [{"isResolved": False, "isOutdated": False}]
                        }
                    }
                }
            }
        }

    monkeypatch.setattr(agent_merge_check, "_request_json", _answer)
    assert (
        agent_merge_check.read_unresolved_thread_count(
            "jl-cmd/claude-dev-env", 1442, "token"
        )
        == 1
    )


def test_read_unresolved_thread_count_rejects_a_query_answer_of_another_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _answer(
        url: str,
        token: str,
        all_payload_fields: object,
    ) -> object:
        if all_payload_fields is None:
            raise agent_merge_check.MergeCheckError("HTTP Error 403: Forbidden")
        return {"errors": [{"message": "Bad credentials"}]}

    monkeypatch.setattr(agent_merge_check, "_request_json", _answer)
    with pytest.raises(agent_merge_check.MergeCheckError):
        agent_merge_check.read_unresolved_thread_count(
            "jl-cmd/claude-dev-env", 1442, "token"
        )


def test_read_settled_pull_request_reads_again_while_the_state_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_answers = [
        _pull_request(mergeable_state="unknown"),
        _pull_request(mergeable_state="unknown"),
        CLEAN_PULL_REQUEST,
    ]
    all_waits: list[float] = []
    monkeypatch.setattr(
        agent_merge_check,
        "read_pull_request",
        lambda slug, number, token: all_answers.pop(0),
    )
    settled = agent_merge_check.read_settled_pull_request(
        "jl-cmd/claude-dev-env", 1442, "token", all_waits.append
    )
    assert settled == CLEAN_PULL_REQUEST
    assert len(all_waits) == 2


def test_read_settled_pull_request_stops_after_its_last_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_waits: list[float] = []
    read_count = 0

    def _unknown(slug: str, number: int, token: str) -> dict[str, object]:
        nonlocal read_count
        read_count += 1
        return _pull_request(mergeable_state="unknown")

    monkeypatch.setattr(agent_merge_check, "read_pull_request", _unknown)
    settled = agent_merge_check.read_settled_pull_request(
        "jl-cmd/claude-dev-env", 1442, "token", all_waits.append
    )
    assert settled["mergeable_state"] == "unknown"
    assert read_count == SETTLE_ATTEMPT_COUNT
    assert len(all_waits) == SETTLE_ATTEMPT_COUNT - 1


def test_read_settled_pull_request_waits_for_no_settled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_waits: list[float] = []
    monkeypatch.setattr(
        agent_merge_check,
        "read_pull_request",
        lambda slug, number, token: CLEAN_PULL_REQUEST,
    )
    agent_merge_check.read_settled_pull_request(
        "jl-cmd/claude-dev-env", 1442, "token", all_waits.append
    )
    assert all_waits == []


def test_a_missing_token_reports_the_error_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"]) == 2


def test_a_ready_pull_request_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        agent_merge_check,
        "read_pull_request",
        lambda slug, number, token: CLEAN_PULL_REQUEST,
    )
    monkeypatch.setattr(agent_merge_check.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        agent_merge_check,
        "read_unresolved_thread_count",
        lambda slug, number, token: 0,
    )
    monkeypatch.setattr(
        agent_merge_check,
        "read_merge_queue_ejection",
        lambda slug, number, token: False,
    )
    assert agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"]) == 0


def test_a_held_pull_request_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        agent_merge_check,
        "read_pull_request",
        lambda slug, number, token: _pull_request(mergeable_state="behind"),
    )
    monkeypatch.setattr(
        agent_merge_check,
        "read_unresolved_thread_count",
        lambda slug, number, token: 0,
    )
    monkeypatch.setattr(
        agent_merge_check,
        "read_merge_queue_ejection",
        lambda slug, number, token: False,
    )
    assert agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"]) == 1


def test_an_unreadable_pull_request_exits_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(slug: str, number: int, token: str) -> dict[str, object]:
        raise agent_merge_check.MergeCheckError("no route to host")

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(agent_merge_check, "read_pull_request", _fail)
    assert agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"]) == 2


HEAD_COMMITTED_AT = "2026-09-26T16:00:00Z"
PULL_REQUEST_4922_HEAD_SHA = "06bc18a1a8761a16e92c1419693a42f22dd4ae7c"
REQUIRED_CHECK_APP_ID = 15368
PULL_REQUEST_4922 = {
    "number": 4922,
    "draft": False,
    "mergeable_state": "blocked",
    "base": {"ref": "main"},
    "head": {"sha": PULL_REQUEST_4922_HEAD_SHA},
}
MAIN_BRANCH_RULES = [
    {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [
                {"context": "Ruff", "integration_id": REQUIRED_CHECK_APP_ID},
                {"context": "Tip Local green", "integration_id": REQUIRED_CHECK_APP_ID},
            ],
        },
    },
    {"type": "merge_queue", "parameters": {"merge_method": "MERGE"}},
]


def _check_run(
    name: str,
    conclusion: str | None,
    run_id: int = 1,
    app_id: int = REQUIRED_CHECK_APP_ID,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "id": run_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "app": {"id": app_id},
    }


def _github_answers(
    all_rules: list[object],
    all_check_runs: list[dict[str, object]],
    behind_by: int,
    all_statuses: list[object] | None = None,
) -> object:
    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        parsed = urllib.parse.urlparse(url)
        if parsed.path.endswith("/pulls/4922"):
            return PULL_REQUEST_4922
        if parsed.path.endswith("/ccr/review_threads"):
            return []
        if "/rules/branches/" in parsed.path:
            return all_rules
        if parsed.path.endswith("/check-runs"):
            check_name = urllib.parse.parse_qs(parsed.query)["check_name"][0]
            return {
                "check_runs": [
                    each_run
                    for each_run in all_check_runs
                    if each_run["name"] == check_name
                ]
            }
        if parsed.path.endswith("/status"):
            return {"statuses": all_statuses or []}
        if "/compare/" in parsed.path:
            return {"behind_by": behind_by, "ahead_by": 1}
        if parsed.path.endswith("/graphql"):
            return _merge_queue_document([])
        raise AssertionError(url)

    return _answer


def _merge_queue_document(all_removals: list[dict[str, object]]) -> object:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "nodes": [{"commit": {"committedDate": HEAD_COMMITTED_AT}}]
                    },
                    "timelineItems": {"nodes": all_removals},
                }
            }
        }
    }


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answer: object,
) -> tuple[int, str]:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(agent_merge_check, "_request_json", answer)
    exit_code = agent_merge_check.main(["jl-cmd/claude-dev-env", "4922"])
    return exit_code, capsys.readouterr().out


def test_a_green_head_behind_a_merge_queue_base_reports_the_behind_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_main(
        monkeypatch,
        capsys,
        _github_answers(
            MAIN_BRANCH_RULES,
            [
                _check_run("Ruff", "success", run_id=11),
                _check_run("Tip Local green", "success", run_id=12),
            ],
            behind_by=225,
        ),
    )
    assert exit_code == 1
    assert BEHIND_MERGE_QUEUE_HOLD_TEMPLATE.format(count=225) in line
    assert BLOCKED_HOLD_REASON not in line
    assert "06bc18a" in line


def test_a_red_required_check_is_named_ahead_of_the_behind_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_main(
        monkeypatch,
        capsys,
        _github_answers(
            MAIN_BRANCH_RULES,
            [
                _check_run("Ruff", "success", run_id=11),
                _check_run("Tip Local green", "failure", run_id=12),
            ],
            behind_by=225,
        ),
    )
    assert exit_code == 1
    assert "Tip Local green (failure)" in line
    assert "Ruff" not in line
    assert "behind" not in line


def test_an_unreadable_branch_rule_keeps_the_generic_blocked_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    routed_answer = _github_answers(MAIN_BRANCH_RULES, [], behind_by=225)

    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        if "/rules/branches/" in url:
            raise agent_merge_check.MergeCheckError("HTTP Error 403: Forbidden")
        return routed_answer(url, token, all_payload_fields)

    exit_code, line = _run_main(monkeypatch, capsys, _answer)
    assert exit_code == 1
    assert BLOCKED_HOLD_REASON in line


def _evidence(
    all_unmet_checks: tuple[str, ...] = (),
    behind_by: int = 0,
    has_merge_queue: bool = True,
) -> agent_merge_check.BlockedEvidence:
    return agent_merge_check.BlockedEvidence(
        all_unmet_checks=all_unmet_checks,
        behind_by=behind_by,
        has_merge_queue=has_merge_queue,
    )


@pytest.mark.parametrize(
    ("evidence", "expected_reason"),
    [
        (_evidence(behind_by=0), BLOCKED_HOLD_REASON),
        (_evidence(behind_by=3, has_merge_queue=False), BLOCKED_HOLD_REASON),
        (
            _evidence(behind_by=3),
            BEHIND_MERGE_QUEUE_HOLD_TEMPLATE.format(count=3),
        ),
    ],
)
def test_a_blocked_head_with_every_required_check_green_reads_its_reason(
    evidence: agent_merge_check.BlockedEvidence,
    expected_reason: str,
) -> None:
    assert (
        agent_merge_check.hold_reason(
            _pull_request(mergeable_state="blocked"), 0, evidence
        )
        == expected_reason
    )


def test_blocked_evidence_is_ignored_for_a_draft() -> None:
    assert (
        agent_merge_check.hold_reason(
            _pull_request(mergeable_state="blocked", draft=True),
            0,
            _evidence(behind_by=3),
        )
        == DRAFT_HOLD_REASON
    )


def test_required_contexts_merge_every_required_status_checks_rule() -> None:
    all_rules = [
        *MAIN_BRANCH_RULES,
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": "Ruff", "integration_id": REQUIRED_CHECK_APP_ID},
                    {"context": "Semgrep"},
                ]
            },
        },
    ]
    assert agent_merge_check.required_contexts(all_rules) == (
        agent_merge_check.RequiredContext("Ruff", REQUIRED_CHECK_APP_ID),
        agent_merge_check.RequiredContext("Tip Local green", REQUIRED_CHECK_APP_ID),
        agent_merge_check.RequiredContext("Semgrep", None),
    )


def test_a_rule_set_without_a_merge_queue_rule_reports_none() -> None:
    assert agent_merge_check.has_merge_queue_rule(MAIN_BRANCH_RULES)
    assert not agent_merge_check.has_merge_queue_rule(MAIN_BRANCH_RULES[:1])


RUFF_FROM_REQUIRED_APP = agent_merge_check.RequiredContext(
    "Ruff", REQUIRED_CHECK_APP_ID
)


@pytest.mark.parametrize(
    ("all_check_runs", "all_statuses", "expected_state"),
    [
        ([_check_run("Ruff", "success")], [], None),
        ([_check_run("Ruff", "skipped")], [], None),
        ([_check_run("Ruff", "failure")], [], "failure"),
        ([_check_run("Ruff", None, status="in_progress")], [], "pending"),
        (
            [
                _check_run("Ruff", "failure", run_id=1),
                _check_run("Ruff", "success", run_id=2),
            ],
            [],
            None,
        ),
        (
            [
                _check_run("Ruff", "success", run_id=2),
                _check_run("Ruff", "failure", run_id=3),
            ],
            [],
            "failure",
        ),
        ([_check_run("Ruff", "success", app_id=1)], [], "missing"),
        ([], [{"context": "Ruff", "state": "success"}], None),
        ([], [{"context": "Ruff", "state": "pending"}], "pending"),
        ([], [{"context": "Ruff", "state": "error"}], "error"),
        ([], [], "missing"),
    ],
)
def test_unmet_check_state_reads_the_newest_report_of_the_required_check(
    all_check_runs: list[object],
    all_statuses: list[object],
    expected_state: str | None,
) -> None:
    assert (
        agent_merge_check.unmet_check_state(
            RUFF_FROM_REQUIRED_APP, all_check_runs, all_statuses
        )
        == expected_state
    )


def test_read_blocked_evidence_reads_the_pull_request_4922_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        _github_answers(
            MAIN_BRANCH_RULES,
            [
                _check_run("Ruff", "success", run_id=11),
                _check_run("Tip Local green", "success", run_id=12),
            ],
            behind_by=225,
        ),
    )
    assert agent_merge_check.read_blocked_evidence(
        "jl-cmd/claude-dev-env", PULL_REQUEST_4922, "token"
    ) == _evidence(behind_by=225)


def test_blocked_hold_reason_names_every_unmet_required_check() -> None:
    reason = agent_merge_check.blocked_hold_reason(
        _evidence(
            all_unmet_checks=("Ruff (failure)", "Tip Local green (missing)"),
            behind_by=225,
        )
    )
    assert "Ruff (failure), Tip Local green (missing)" in reason
    assert "behind" not in reason


QUEUED_PULL_REQUEST = {
    "number": 1442,
    "draft": False,
    "mergeable_state": "clean",
    "base": {"ref": "main"},
    "head": {"sha": "ab845eb6945650055ebe852312a9057b9f067d6a"},
}


def _removal(created_at: str, reason: str) -> dict[str, object]:
    return {"createdAt": created_at, "reason": reason}


def _merge_queue_answers(
    all_removals: list[dict[str, object]],
) -> object:
    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        if url.endswith("/pulls/1442"):
            return QUEUED_PULL_REQUEST
        if url.endswith("/ccr/review_threads"):
            return []
        if url.endswith("/graphql"):
            return _merge_queue_document(all_removals)
        raise AssertionError(url)

    return _answer


def _run_queued_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    all_removals: list[dict[str, object]],
) -> tuple[int, str]:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        agent_merge_check, "_request_json", _merge_queue_answers(all_removals)
    )
    exit_code = agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"])
    return exit_code, capsys.readouterr().out


def test_a_head_ejected_from_the_merge_queue_for_failed_checks_holds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_queued_main(
        monkeypatch,
        capsys,
        [
            _removal("2026-09-26T15:09:20Z", "failed_checks"),
            _removal("2026-09-26T17:11:35Z", "failed_checks"),
        ],
    )
    assert exit_code == 1
    assert line.startswith(HOLD_VERDICT_LABEL)
    assert "merge queue" in line
    assert "failed checks" in line
    assert "merge_group" in line
    assert "gh-readonly-queue/main/pr-1442-<sha>" in line
    assert "before you enqueue it again" in line


def test_a_fix_pushed_after_the_merge_queue_ejection_clears_the_hold(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_queued_main(
        monkeypatch,
        capsys,
        [_removal("2026-09-26T15:09:20Z", "failed_checks")],
    )
    assert exit_code == 0
    assert line.startswith(MERGE_VERDICT_LABEL)


def test_a_manual_merge_queue_removal_does_not_hold(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_queued_main(
        monkeypatch,
        capsys,
        [
            _removal("2026-09-26T15:09:20Z", "failed_checks"),
            _removal("2026-09-26T17:58:17Z", "manual"),
        ],
    )
    assert exit_code == 0
    assert line.startswith(MERGE_VERDICT_LABEL)


def test_a_repository_with_no_merge_queue_removal_may_merge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_queued_main(monkeypatch, capsys, [])
    assert exit_code == 0
    assert line.startswith(MERGE_VERDICT_LABEL)


def test_a_merge_queue_answer_of_another_shape_exits_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    routed_answer = _merge_queue_answers([])

    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        if url.endswith("/graphql"):
            return {"errors": [{"message": "Bad credentials"}]}
        return routed_answer(url, token, all_payload_fields)

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(agent_merge_check, "_request_json", _answer)
    assert agent_merge_check.main(["jl-cmd/claude-dev-env", "1442"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("all_removals", "expected_ejection"),
    [
        ([_removal("2026-09-26T17:11:35Z", "failed_checks")], True),
        ([_removal("2026-09-26T15:09:20Z", "failed_checks")], False),
        ([_removal("2026-09-26T17:58:17Z", "manual")], False),
        ([], False),
    ],
)
def test_read_merge_queue_ejection_compares_failed_checks_removals_to_the_head(
    monkeypatch: pytest.MonkeyPatch,
    all_removals: list[dict[str, object]],
    expected_ejection: bool,
) -> None:
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        lambda url, token, all_payload_fields: _merge_queue_document(all_removals),
    )
    assert (
        agent_merge_check.read_merge_queue_ejection(
            "jl-cmd/claude-dev-env", 1442, "token"
        )
        is expected_ejection
    )


PULL_REQUEST_5330_HEAD_SHA = "bd616254075d6d2bbe58acadca3d6a30bf8ee814"
PULL_REQUEST_5330 = {
    "number": 5330,
    "draft": False,
    "mergeable_state": "unstable",
    "base": {"ref": "main"},
    "head": {"sha": PULL_REQUEST_5330_HEAD_SHA},
}
COPILOT_REVIEWER_APP_ID = 946600
PULL_REQUEST_5330_CHECK_RUNS = [
    _check_run("Review closure", "success", run_id=110871328668),
    _check_run("Review closure", "cancelled", run_id=110871409317),
    _check_run("Review closure", "cancelled", run_id=110871412010),
    _check_run("Review closure", "cancelled", run_id=110871418946),
    _check_run("Review closure", "cancelled", run_id=110871420919),
    _check_run("Review closure", "success", run_id=110874389252),
    _check_run("Ruff", "cancelled", run_id=110871770000),
    _check_run("Ruff", "success", run_id=110887099099),
    _check_run("Tip Local green", "success", run_id=110873242269),
    _check_run("Merge queue build verdict", "skipped", run_id=110887297809),
    _check_run(
        "copilot-pull-request-reviewer",
        "success",
        run_id=110871360430,
        app_id=COPILOT_REVIEWER_APP_ID,
    ),
]
NEWEST_REVIEW_CLOSURE_CANCELLED = [
    *PULL_REQUEST_5330_CHECK_RUNS,
    _check_run("Review closure", "cancelled", run_id=110890000000),
]


def test_superseded_cancelled_runs_leave_no_unmet_newest_check() -> None:
    assert agent_merge_check.unmet_newest_checks(PULL_REQUEST_5330_CHECK_RUNS, []) == ()


@pytest.mark.parametrize(
    ("all_check_runs", "all_statuses", "expected_checks"),
    [
        (NEWEST_REVIEW_CLOSURE_CANCELLED, [], ("Review closure (cancelled)",)),
        (
            [_check_run("Ruff", None, run_id=2, status="in_progress")],
            [],
            ("Ruff (pending)",),
        ),
        (
            [
                _check_run("Ruff", "success", run_id=2),
                _check_run("Ruff", "failure", run_id=5, app_id=1),
            ],
            [],
            ("Ruff (failure)",),
        ),
        (
            PULL_REQUEST_5330_CHECK_RUNS,
            [
                {"context": "local-checks", "state": "success"},
                {"context": "Semgrep", "state": "failure"},
            ],
            ("Semgrep (failure)",),
        ),
    ],
)
def test_unmet_newest_checks_names_each_check_whose_newest_report_is_not_passing(
    all_check_runs: list[object],
    all_statuses: list[object],
    expected_checks: tuple[str, ...],
) -> None:
    assert (
        agent_merge_check.unmet_newest_checks(all_check_runs, all_statuses)
        == expected_checks
    )


def test_an_unstable_head_whose_newest_runs_pass_may_merge() -> None:
    assert (
        agent_merge_check.hold_reason(
            _pull_request(mergeable_state="unstable"), 0, all_unstable_checks=()
        )
        is None
    )


def test_an_unstable_head_whose_newest_runs_pass_still_holds_on_an_open_thread() -> (
    None
):
    reason = agent_merge_check.hold_reason(
        _pull_request(mergeable_state="unstable"), 1, all_unstable_checks=()
    )
    assert reason is not None
    assert "1 review thread" in reason


def test_an_unstable_head_names_the_check_whose_newest_run_failed() -> None:
    reason = agent_merge_check.hold_reason(
        _pull_request(mergeable_state="unstable"),
        0,
        all_unstable_checks=("Review closure (cancelled)",),
    )
    assert reason is not None
    assert "Review closure (cancelled)" in reason


def _unstable_answers(
    all_check_runs: list[dict[str, object]],
    all_threads: list[object] | None = None,
    all_statuses: list[object] | None = None,
) -> object:
    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        parsed = urllib.parse.urlparse(url)
        if parsed.path.endswith("/pulls/5330"):
            return PULL_REQUEST_5330
        if parsed.path.endswith("/ccr/review_threads"):
            return all_threads or []
        if parsed.path.endswith("/graphql"):
            return _merge_queue_document([])
        if parsed.path.endswith("/check-runs"):
            return {"check_runs": _requested_page(parsed.query, all_check_runs)}
        if parsed.path.endswith("/status"):
            return {"statuses": _requested_page(parsed.query, all_statuses or [])}
        raise AssertionError(url)

    return _answer


def _requested_page(query: str, all_records: list[object]) -> list[object]:
    all_parameters = urllib.parse.parse_qs(query)
    page_size = int(all_parameters["per_page"][0])
    page_number = int(all_parameters["page"][0])
    first_index = (page_number - 1) * page_size
    return all_records[first_index : first_index + page_size]


def _run_unstable_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answer: object,
) -> tuple[int, str]:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(agent_merge_check, "_request_json", answer)
    exit_code = agent_merge_check.main(["jl-cmd/claude-dev-env", "5330"])
    return exit_code, capsys.readouterr().out


def test_the_pull_request_5330_shape_reads_merge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_unstable_main(
        monkeypatch, capsys, _unstable_answers(PULL_REQUEST_5330_CHECK_RUNS)
    )
    assert exit_code == 0
    assert line.startswith(MERGE_VERDICT_LABEL)
    assert "bd61625" in line


def test_a_newest_run_cancellation_on_an_unstable_head_holds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, line = _run_unstable_main(
        monkeypatch, capsys, _unstable_answers(NEWEST_REVIEW_CLOSURE_CANCELLED)
    )
    assert exit_code == 1
    assert line.startswith(HOLD_VERDICT_LABEL)
    assert "Review closure (cancelled)" in line


def test_an_unreadable_check_listing_keeps_the_generic_unstable_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    routed_answer = _unstable_answers(PULL_REQUEST_5330_CHECK_RUNS)

    def _answer(url: str, token: str, all_payload_fields: object) -> object:
        if "/check-runs" in url:
            raise agent_merge_check.MergeCheckError("HTTP Error 403: Forbidden")
        return routed_answer(url, token, all_payload_fields)

    exit_code, line = _run_unstable_main(monkeypatch, capsys, _answer)
    assert exit_code == 1
    assert UNSTABLE_HOLD_REASON in line


def test_read_unstable_checks_reads_every_page_of_check_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_passing_runs = [
        _check_run(f"Shard {each_index}", "success", run_id=each_index)
        for each_index in range(1, 151)
    ]
    all_runs_with_late_failure = [
        *all_passing_runs,
        _check_run("Shard 150", "failure", run_id=151),
    ]
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        _unstable_answers(all_runs_with_late_failure),
    )
    assert agent_merge_check.read_unstable_checks(
        "jl-cmd/claude-dev-env", PULL_REQUEST_5330_HEAD_SHA, "token"
    ) == ("Shard 150 (failure)",)


def test_read_unstable_checks_reads_every_page_of_commit_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_statuses_with_late_failure = [
        *(
            {"context": f"Gate {each_index}", "state": "success"}
            for each_index in range(1, 121)
        ),
        {"context": "Gate 121", "state": "failure"},
    ]
    monkeypatch.setattr(
        agent_merge_check,
        "_request_json",
        _unstable_answers(
            PULL_REQUEST_5330_CHECK_RUNS,
            all_statuses=all_statuses_with_late_failure,
        ),
    )
    assert agent_merge_check.read_unstable_checks(
        "jl-cmd/claude-dev-env", PULL_REQUEST_5330_HEAD_SHA, "token"
    ) == ("Gate 121 (failure)",)
