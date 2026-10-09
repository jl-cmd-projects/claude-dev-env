from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import review_closure as command
import review_closure_model as model
from dev_env_scripts_constants.review_closure_constants import (
    APPROVALS_CHECK_NAME,
    APPROVALS_OPEN_REASON,
    RED_CIRCLE_MARKER,
    RED_CIRCLE_OPEN_REASON,
    TOP_LEVEL_OPEN_REASON_TEMPLATE,
    UNANSWERED_OPEN_REASON,
    UNNAMED_THREAD_SUBJECT,
)

DRIVING_AGENT = frozenset({"claude[bot]"})
REVIEW_BOT = "qodo-merge-pro[bot]"
REVIEWER = "maintainer"


def thread(
    *,
    all_comments: tuple[model.ReviewComment, ...],
    is_resolved: bool = False,
    is_outdated: bool = False,
    subject: str = "scripts/example.py",
) -> model.ReviewThread:
    return model.ReviewThread(
        subject=subject,
        is_resolved=is_resolved,
        is_outdated=is_outdated,
        all_comments=all_comments,
    )


def bot_comment(body: str = "This call drops the return value.") -> model.ReviewComment:
    return model.ReviewComment(author_login=REVIEW_BOT, body=body)


def agent_comment(body: str = "Fixed in the next push.") -> model.ReviewComment:
    return model.ReviewComment(author_login="claude[bot]", body=body)


def should_report_an_unanswered_thread_as_open() -> None:
    finding = model.thread_finding(thread(all_comments=(bot_comment(),)), DRIVING_AGENT)

    assert finding == model.OpenFinding(
        subject="scripts/example.py", reason=UNANSWERED_OPEN_REASON
    )


def should_close_a_thread_the_driving_agent_replied_to() -> None:
    answered = thread(all_comments=(bot_comment(), agent_comment()))

    assert model.thread_finding(answered, DRIVING_AGENT) is None


def should_leave_a_thread_open_when_only_another_bot_replied() -> None:
    other_bot = model.ReviewComment(author_login="graphite[bot]", body="Same here.")
    noisy = thread(all_comments=(bot_comment(), other_bot))

    assert model.thread_finding(noisy, DRIVING_AGENT) is not None


def should_close_an_outdated_thread_without_a_reply() -> None:
    replaced = thread(all_comments=(bot_comment(),), is_outdated=True)

    assert model.thread_finding(replaced, DRIVING_AGENT) is None


def should_close_a_resolved_ordinary_thread() -> None:
    resolved = thread(all_comments=(bot_comment(),), is_resolved=True)

    assert model.thread_finding(resolved, DRIVING_AGENT) is None


def should_keep_a_resolved_red_circle_finding_open() -> None:
    blocking = thread(
        all_comments=(bot_comment(f"{RED_CIRCLE_MARKER} This drops user input."),),
        is_resolved=True,
    )

    finding = model.thread_finding(blocking, DRIVING_AGENT)

    assert finding == model.OpenFinding(
        subject="scripts/example.py", reason=RED_CIRCLE_OPEN_REASON
    )


def should_close_a_red_circle_finding_the_agent_answered() -> None:
    answered = thread(
        all_comments=(
            bot_comment(f"{RED_CIRCLE_MARKER} This drops user input."),
            agent_comment(),
        )
    )

    assert model.thread_finding(answered, DRIVING_AGENT) is None


def should_close_a_red_circle_finding_a_push_replaced() -> None:
    replaced = thread(
        all_comments=(bot_comment(f"{RED_CIRCLE_MARKER} This drops user input."),),
        is_outdated=True,
    )

    assert model.thread_finding(replaced, DRIVING_AGENT) is None


def should_close_a_thread_the_driving_agent_opened() -> None:
    own = thread(all_comments=(agent_comment("Reading this back for the reviewer."),))

    assert model.thread_finding(own, DRIVING_AGENT) is None


def should_report_the_driving_agent_as_the_thread_author() -> None:
    own = thread(all_comments=(agent_comment(),))

    assert model.opened_by_driver(own, DRIVING_AGENT) is True
    assert model.opened_by_driver(thread(all_comments=()), DRIVING_AGENT) is False


def should_report_a_reply_from_the_driving_agent() -> None:
    answered = thread(all_comments=(bot_comment(), agent_comment()))

    assert model.has_driver_reply(answered, DRIVING_AGENT) is True
    assert (
        model.has_driver_reply(thread(all_comments=(bot_comment(),)), DRIVING_AGENT)
        is False
    )


def should_report_a_blocking_approvals_row_as_open() -> None:
    all_findings = model.all_open_findings((), (), DRIVING_AGENT, "failure")

    assert all_findings == (
        model.OpenFinding(subject=APPROVALS_CHECK_NAME, reason=APPROVALS_OPEN_REASON),
    )


def should_pass_when_approvals_succeeds_and_no_thread_waits() -> None:
    answered = thread(all_comments=(bot_comment(), agent_comment()))

    assert model.all_open_findings((answered,), (), DRIVING_AGENT, "success") == ()


def should_pass_where_the_approvals_check_does_not_run() -> None:
    assert model.all_open_findings((), (), DRIVING_AGENT, None) == ()


def should_report_every_open_thread_and_the_approvals_row() -> None:
    first = thread(all_comments=(bot_comment(),), subject="scripts/first.py")
    second = thread(all_comments=(bot_comment(),), subject="scripts/second.py")

    all_findings = model.all_open_findings(
        (first, second), (), DRIVING_AGENT, "action_required"
    )

    assert [each.subject for each in all_findings] == [
        "scripts/first.py",
        "scripts/second.py",
        APPROVALS_CHECK_NAME,
    ]


def should_read_a_graphql_thread_record() -> None:
    parsed = model.parse_thread(
        {
            "path": "scripts/example.py",
            "isResolved": False,
            "isOutdated": True,
            "comments": {
                "nodes": [
                    {"body": "A finding.", "author": {"login": REVIEW_BOT}},
                    {"body": "Answered.", "author": {"login": "claude[bot]"}},
                ]
            },
        }
    )

    assert parsed == model.ReviewThread(
        subject="scripts/example.py",
        is_resolved=False,
        is_outdated=True,
        all_comments=(
            model.ReviewComment(author_login=REVIEW_BOT, body="A finding."),
            model.ReviewComment(author_login="claude[bot]", body="Answered."),
        ),
    )


def should_read_a_rest_thread_record() -> None:
    parsed = model.parse_thread(
        {
            "resolved": True,
            "outdated": False,
            "comments": [{"body": "A finding.", "user": {"login": REVIEW_BOT}}],
        }
    )

    assert parsed == model.ReviewThread(
        subject=UNNAMED_THREAD_SUBJECT,
        is_resolved=True,
        is_outdated=False,
        all_comments=(model.ReviewComment(author_login=REVIEW_BOT, body="A finding."),),
    )


def should_read_a_thread_that_carries_no_comments() -> None:
    parsed = model.parse_thread({"path": "scripts/example.py"})

    assert parsed.all_comments == ()
    assert model.carries_red_circle(parsed) is False


def should_find_the_approvals_conclusion_among_the_check_runs() -> None:
    all_check_runs = [
        {"name": "Python suite (ubuntu)", "conclusion": "success"},
        {"name": APPROVALS_CHECK_NAME, "conclusion": "failure"},
    ]

    assert model.approvals_conclusion(all_check_runs) == "failure"


def should_report_no_conclusion_where_approvals_does_not_run() -> None:
    assert model.approvals_conclusion([{"name": "Python suite (ubuntu)"}]) is None


def should_count_the_pull_request_author_as_the_driving_agent() -> None:
    all_logins = model.driver_logins({"user": {"login": "claude[bot]"}}, [])

    assert all_logins == frozenset({"claude[bot]"})


def should_add_each_login_named_on_the_command_line() -> None:
    all_logins = model.driver_logins({"user": {"login": "claude[bot]"}}, ["octocat"])

    assert all_logins == frozenset({"claude[bot]", "octocat"})


def should_read_the_head_commit_from_the_pull_request() -> None:
    assert model.head_sha({"head": {"sha": "ab845eb"}}) == "ab845eb"
    assert model.head_sha({}) == ""


def should_name_the_open_count_in_the_verdict_line() -> None:
    line = model.verdict_line(
        "jl-cmd/claude-dev-env",
        {"number": 1442, "head": {"sha": "ab845ebc0ffee11"}},
        (model.OpenFinding(subject="scripts/example.py", reason="waiting"),),
    )

    assert line.startswith("OPEN jl-cmd/claude-dev-env#1442 ab845eb :: 1 review")


def should_name_the_closed_state_in_the_verdict_line() -> None:
    line = model.verdict_line(
        "jl-cmd/claude-dev-env",
        {"number": 1442, "head": {"sha": "ab845ebc0ffee11"}},
        (),
    )

    assert line.startswith("CLOSED jl-cmd/claude-dev-env#1442 ab845eb ::")


def should_join_a_session_route_thread_with_its_comments() -> None:
    parsed = model.parse_thread(
        {"path": "scripts/example.py", "resolved": False, "comment_ids": [11, 12]},
        {
            11: {"body": "A finding.", "user": {"login": REVIEW_BOT}},
            12: {"body": "Answered.", "user": {"login": "claude[bot]"}},
        },
    )

    assert [each.author_login for each in parsed.all_comments] == [
        REVIEW_BOT,
        "claude[bot]",
    ]
    assert model.thread_finding(parsed, DRIVING_AGENT) is None


def should_skip_a_comment_identifier_the_listing_does_not_carry() -> None:
    parsed = model.parse_thread(
        {"path": "scripts/example.py", "comment_ids": [11, 99]},
        {11: {"body": "A finding.", "user": {"login": REVIEW_BOT}}},
    )

    assert len(parsed.all_comments) == 1


def should_key_the_review_comments_by_identifier() -> None:
    all_comment_records = model.comment_records_by_id(
        [{"id": 11, "body": "A finding."}, {"body": "no identifier"}, "not a record"]
    )

    assert all_comment_records == {11: {"id": 11, "body": "A finding."}}


BOT_SUMMARY_URL = "https://github.com/jl-cmd/claude-dev-env/pull/7#issuecomment-1"


def at_minute(minute: int) -> datetime:
    return datetime.fromisoformat(f"2026-09-26T12:{minute:02d}:00+00:00")


def top_level_comment(
    author_login: str,
    posted_minute: int,
    edited_minute: int | None = None,
    url: str = BOT_SUMMARY_URL,
    is_bot: bool = True,
    is_notice: bool = False,
) -> model.TopLevelComment:
    return model.TopLevelComment(
        identifier=posted_minute,
        author_login=author_login,
        is_bot=is_bot,
        is_notice=is_notice,
        created_at=at_minute(posted_minute),
        updated_at=at_minute(posted_minute if edited_minute is None else edited_minute),
        url=url,
    )


def should_report_a_bot_top_level_comment_with_no_driver_comment() -> None:
    all_findings = model.top_level_findings(
        (top_level_comment(REVIEW_BOT, 1),), DRIVING_AGENT
    )

    assert all_findings == (
        model.OpenFinding(
            subject=BOT_SUMMARY_URL,
            reason=TOP_LEVEL_OPEN_REASON_TEMPLATE.format(author=REVIEW_BOT),
        ),
    )


def should_close_a_bot_top_level_comment_the_driver_posted_after() -> None:
    all_comments = (
        top_level_comment(REVIEW_BOT, 1),
        top_level_comment("claude[bot]", 2),
    )

    assert model.top_level_findings(all_comments, DRIVING_AGENT) == ()


def should_close_every_earlier_comment_with_one_driver_comment() -> None:
    all_comments = (
        top_level_comment(REVIEW_BOT, 1),
        top_level_comment("graphite-app[bot]", 2),
        top_level_comment("claude[bot]", 3),
    )

    assert model.top_level_findings(all_comments, DRIVING_AGENT) == ()


def should_reopen_a_person_comment_edited_after_the_driver_reply() -> None:
    all_comments = (
        top_level_comment(REVIEWER, 1, edited_minute=5, is_bot=False),
        top_level_comment("claude[bot]", 2),
    )

    all_findings = model.top_level_findings(all_comments, DRIVING_AGENT)

    assert [each.subject for each in all_findings] == [BOT_SUMMARY_URL]


def should_keep_a_bot_summary_closed_when_edited_after_the_driver_reply() -> None:
    all_comments = (
        top_level_comment(REVIEW_BOT, 1, edited_minute=5),
        top_level_comment("claude[bot]", 2),
    )

    assert model.top_level_findings(all_comments, DRIVING_AGENT) == ()


def should_leave_a_bot_comment_posted_after_the_driver_open() -> None:
    all_comments = (
        top_level_comment("claude[bot]", 1),
        top_level_comment(REVIEW_BOT, 2),
    )

    assert len(model.top_level_findings(all_comments, DRIVING_AGENT)) == 1


def should_never_report_a_driver_top_level_comment() -> None:
    all_comments = (top_level_comment("claude[bot]", 1, edited_minute=9),)

    assert model.top_level_findings(all_comments, DRIVING_AGENT) == ()


def should_find_the_latest_driver_top_level_comment_time() -> None:
    all_comments = (
        top_level_comment("claude[bot]", 1),
        top_level_comment(REVIEW_BOT, 2),
        top_level_comment("claude[bot]", 3, edited_minute=9),
    )

    assert model.latest_driver_comment_time(all_comments, DRIVING_AGENT) == at_minute(3)


def should_find_no_driver_time_when_the_driver_posted_nothing() -> None:
    all_comments = (top_level_comment(REVIEW_BOT, 1),)

    assert model.latest_driver_comment_time(all_comments, DRIVING_AGENT) is None


def should_close_a_bot_comment_last_edited_at_the_driver_time() -> None:
    comment = top_level_comment(REVIEW_BOT, 1, edited_minute=4)

    assert model.top_level_finding(comment, DRIVING_AGENT, at_minute(4)) is None


def should_open_a_person_comment_edited_after_the_driver_time() -> None:
    comment = top_level_comment(REVIEWER, 1, edited_minute=5, is_bot=False)

    assert model.top_level_finding(
        comment, DRIVING_AGENT, at_minute(4)
    ) == model.OpenFinding(
        subject=BOT_SUMMARY_URL,
        reason=TOP_LEVEL_OPEN_REASON_TEMPLATE.format(author=REVIEWER),
    )


def should_close_a_bot_comment_posted_before_and_edited_after_the_driver_time() -> (
    None
):
    comment = top_level_comment(REVIEW_BOT, 1, edited_minute=5)

    assert model.top_level_finding(comment, DRIVING_AGENT, at_minute(4)) is None


def should_open_a_bot_comment_posted_after_the_driver_time() -> None:
    comment = top_level_comment(REVIEW_BOT, 5)

    assert model.top_level_finding(
        comment, DRIVING_AGENT, at_minute(4)
    ) == model.OpenFinding(
        subject=BOT_SUMMARY_URL,
        reason=TOP_LEVEL_OPEN_REASON_TEMPLATE.format(author=REVIEW_BOT),
    )


def should_close_a_bot_notice_posted_after_the_driver_time() -> None:
    comment = top_level_comment(REVIEW_BOT, 5, is_notice=True)

    assert model.top_level_finding(comment, DRIVING_AGENT, at_minute(4)) is None


@pytest.mark.parametrize(
    "body",
    [
        "No code changes since the last review \u2014 review skipped",
        "[Code review](https://example.test/pull/7#issuecomment-1) by qodo was "
        "updated up to the latest commit https://example.test/commit/abc",
        "<!-- graphite-review-comment -->\n\n### Graphite AI review",
        "<h3>PR Summary by Qodo</h3>\n\nBuild the default map per instance",
        "\n<h3>Qodo is busy working</h3>\n\nCheck back in a few minutes.",
        "\n<h3>Code Review by Qodo</h3>\n<code>\U0001f41e Bugs (0)</code>\n\n"
        "<h3>Great, no issues found!</h3>\nQodo reviewed your code",
    ],
)
def should_read_a_bot_notice_as_a_notice(body: str) -> None:
    comment = model.parse_top_level_comment(notice_record(body, "Bot"))

    assert comment.is_notice
    assert model.top_level_findings((comment,), DRIVING_AGENT) == ()


def should_read_a_person_pasting_notice_text_as_a_comment() -> None:
    comment = model.parse_top_level_comment(
        notice_record("No code changes since the last review", "User")
    )

    assert not comment.is_notice
    assert len(model.top_level_findings((comment,), DRIVING_AGENT)) == 1


def should_read_a_bot_finding_as_a_comment() -> None:
    comment = model.parse_top_level_comment(
        notice_record("A finding: the loop never ends.", "Bot")
    )

    assert not comment.is_notice


def should_read_a_qodo_review_with_bugs_as_a_comment() -> None:
    comment = model.parse_top_level_comment(
        notice_record(
            "\n<h3>Code Review by Qodo</h3>\n<code>\U0001f41e Bugs (2)</code>\n\n"
            "1. The loop never ends.",
            "Bot",
        )
    )

    assert not comment.is_notice


def notice_record(body: str, user_type: str) -> dict[str, object]:
    return {
        "id": 1,
        "user": {"login": REVIEW_BOT, "type": user_type},
        "body": body,
        "created_at": "2026-09-26T12:05:00+00:00",
        "updated_at": "2026-09-26T12:05:00+00:00",
        "html_url": BOT_SUMMARY_URL,
    }


def should_count_waiting_top_level_comments_among_the_findings() -> None:
    all_findings = model.all_open_findings(
        (), (top_level_comment(REVIEW_BOT, 1),), DRIVING_AGENT, None
    )

    assert [each.subject for each in all_findings] == [BOT_SUMMARY_URL]


def should_read_a_top_level_comment_record() -> None:
    comment = model.parse_top_level_comment(
        {
            "id": 1,
            "user": {"login": REVIEW_BOT, "type": "Bot"},
            "created_at": "2026-09-26T12:01:00Z",
            "updated_at": "2026-09-26T12:05:00Z",
            "html_url": BOT_SUMMARY_URL,
        }
    )

    assert comment == top_level_comment(REVIEW_BOT, 1, edited_minute=5)


def should_read_a_person_top_level_comment_record() -> None:
    comment = model.parse_top_level_comment(
        {
            "id": 1,
            "user": {"login": REVIEWER, "type": "User"},
            "created_at": "2026-09-26T12:01:00Z",
            "updated_at": "2026-09-26T12:05:00Z",
            "html_url": BOT_SUMMARY_URL,
        }
    )

    assert comment == top_level_comment(REVIEWER, 1, edited_minute=5, is_bot=False)


def should_read_a_bot_comment_carrying_a_repository_marker_as_a_notice() -> None:
    body = "<!-- vendor:trial-expiring -->\n\nYour trial ends soon."

    assert not model.parse_top_level_comment(notice_record(body, "Bot")).is_notice
    assert model.parse_top_level_comment(
        notice_record(body, "Bot"), ("<!-- vendor:trial-expiring -->",)
    ).is_notice


def should_read_a_person_carrying_a_repository_marker_as_a_comment() -> None:
    comment = model.parse_top_level_comment(
        notice_record("<!-- vendor:trial-expiring -->", "User"),
        ("<!-- vendor:trial-expiring -->",),
    )

    assert not comment.is_notice


CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "test_files/review_closure/codex_comments.json")
    .read_text(encoding="utf-8")
)
DRIVERS = frozenset({CASES[0]["driver_login"]})
SLUG = "jl-cmd-projects/claude-dev-env"


def _comments(case: dict) -> tuple[model.TopLevelComment, ...]:
    return tuple(model.parse_top_level_comment(record) for record in case["comments"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["number"]))
def should_replay_clean_queue_comments_through_the_command(
    case: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pr = {"number": case["number"], "head": {"sha": case["head"]},
          "user": {"login": next(iter(DRIVERS))}}
    monkeypatch.setattr(command, "github_token", lambda: "fixture-token")
    monkeypatch.setattr(command, "read_pull_request", lambda *_: pr)
    monkeypatch.setattr(command, "read_review_threads", lambda *_: ())
    monkeypatch.setattr(command, "read_top_level_comments", lambda *_: _comments(case))
    monkeypatch.setattr(command, "read_approvals_conclusion", lambda *_: None)

    assert command.main([SLUG, str(case["number"])]) == 0
    assert capsys.readouterr().out.startswith(f"CLOSED {SLUG}#{case['number']}")


@pytest.mark.parametrize("body", ["@codex review", "@codex security review"])
def should_treat_a_command_only_request_as_a_notice(body: str) -> None:
    record = copy.deepcopy(CASES[0]["comments"][0])
    record["body"] = body

    assert model.parse_top_level_comment(record).is_notice


def should_not_credit_a_driver_review_request_as_a_bug_reply() -> None:
    request = copy.deepcopy(CASES[0]["comments"][0])
    request["user"]["login"] = next(iter(DRIVERS))
    bug = copy.deepcopy(request)
    bug["user"]["login"] = "maintainer"
    bug["body"] = "The rollback loses the saved profile."
    bug["created_at"] = bug["updated_at"] = "2026-10-06T11:00:00Z"
    comments = tuple(model.parse_top_level_comment(record) for record in (bug, request))

    assert len(model.top_level_findings(comments, DRIVERS)) == 1
    assert model.latest_driver_comment_time(comments, DRIVERS) is None


@pytest.mark.parametrize("user_type,login", [
    ("User", "chatgpt-codex-connector[bot]"),
    ("Bot", "untrusted[bot]"),
    ("User", "maintainer"),
])
@pytest.mark.parametrize("record_index", [1, 2])
@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["number"]))
def should_retain_a_notice_pasted_by_an_untrusted_author(
    user_type: str, login: str, record_index: int, case: dict
) -> None:
    record = copy.deepcopy(case["comments"][record_index])
    record["user"] = {"type": user_type, "login": login}
    comment = model.parse_top_level_comment(record)

    assert not comment.is_notice
    assert len(model.top_level_findings((comment,), DRIVERS)) == 1


@pytest.mark.parametrize("record_index", [0, 1, 2])
@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["number"]))
def should_retain_a_command_or_notice_with_an_appended_finding(record_index: int, case: dict) -> None:
    record = copy.deepcopy(case["comments"][record_index])
    record["body"] += "\n\n[P1] The rollback loses the saved profile."
    comment = model.parse_top_level_comment(record)

    assert not comment.is_notice
    assert len(model.top_level_findings((comment,), DRIVERS)) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["number"]))
def should_retain_a_finding_inside_the_clean_review_sentence(case: dict) -> None:
    record = copy.deepcopy(case["comments"][2])
    record["body"] = record["body"].replace(
        "Didn't find any major issues.", "Didn't find any major issues. [P1] The rollback loses a profile."
    )

    assert not model.parse_top_level_comment(record).is_notice


def should_retain_a_finding_inside_pasted_notice_metadata() -> None:
    record = copy.deepcopy(CASES[0]["comments"][2])
    record["body"] = record["body"].replace(
        "</details>", "[P1] The rollback loses the saved profile.\n</details>"
    )

    assert not model.parse_top_level_comment(record).is_notice


def should_keep_an_inline_finding_open_beside_clean_notices() -> None:
    thread = model.ReviewThread(
        subject="bin/install.mjs", is_resolved=False, is_outdated=False,
        all_comments=(model.ReviewComment("reviewer", "[P1] The rollback loses a profile."),),
    )

    findings = model.all_open_findings((thread,), _comments(CASES[0]), DRIVERS, None)

    assert len(findings) == 1
    assert findings[0].subject == "bin/install.mjs"


def should_keep_a_top_level_bug_open_after_a_stale_clean_verdict() -> None:
    bug = copy.deepcopy(CASES[0]["comments"][0])
    bug["user"]["login"] = "maintainer"
    bug["body"] = "[P1] The rollback loses the saved profile."
    clean = copy.deepcopy(CASES[0]["comments"][2])
    clean["body"] = clean["body"].replace("e123a99375", "aaaaaaaaaa")
    comments = tuple(model.parse_top_level_comment(record) for record in (bug, clean))

    assert len(model.top_level_findings(comments, DRIVERS)) == 1


def should_keep_a_blocking_approval_open_beside_clean_notices() -> None:
    findings = model.all_open_findings((), _comments(CASES[0]), DRIVERS, "failure")

    assert len(findings) == 1
    assert findings[0].subject == "Claude Approvals"
