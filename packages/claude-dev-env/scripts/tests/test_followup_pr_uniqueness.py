from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import followup_pr_uniqueness as command
from pr_verification.github_parsing import GitHubError

AFTER_RULE = "2026-10-05T00:00:00Z"
BEFORE_RULE = "2026-10-04T03:00:00Z"


def pull_request(number: int, body: str, created_at: str = AFTER_RULE) -> dict[str, object]:
    return {
        "number": number,
        "body": body,
        "created_at": created_at,
        "html_url": f"https://github.com/jl-cmd/claude-dev-env/pull/{number}",
    }


def test_second_followup_fails_naming_the_first() -> None:
    first = pull_request(1900, "Follow-up to #1731")
    second = pull_request(1901, "follow-up to #1731: one more")
    message = command.duplicate_message(second, [first, second])
    assert message is not None
    assert "Add this finding to the open follow-up pull request #1900" in message


def test_first_followup_stays_green_after_a_duplicate_opens() -> None:
    first = pull_request(1900, "Follow-up to #1731")
    second = pull_request(1901, "Follow-up to #1731")
    assert command.duplicate_message(first, [first, second]) is None


def test_followups_opened_before_the_rule_do_not_count() -> None:
    legacy = pull_request(1769, "Follow-up to #1731", BEFORE_RULE)
    assert command.duplicate_message(pull_request(1900, "Follow-up to #1731"), [legacy]) is None
    later_legacy = pull_request(1770, "Follow-up to #1731", BEFORE_RULE)
    assert command.duplicate_message(later_legacy, [legacy, later_legacy]) is None


def test_other_parent_and_non_followup_pass() -> None:
    first = pull_request(1900, "Follow-up to #173")
    assert command.duplicate_message(pull_request(1901, "Follow-up to #1731"), [first]) is None
    assert command.duplicate_message(pull_request(1901, "Adds a hook."), [first]) is None


def test_main_exits_one_on_duplicate_and_two_on_read_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = pull_request(1900, "Follow-up to #1731")
    second = pull_request(1901, "Follow-up to #1731")
    monkeypatch.setattr(command, "github_token", lambda: "token")
    monkeypatch.setattr(command, "read_pull_request", lambda slug, number, token: second)
    monkeypatch.setattr(command, "request_json", lambda method, url, token, body: [first, second])
    assert command.main(["jl-cmd/claude-dev-env", "1901"]) == 1
    assert "#1900" in capsys.readouterr().out

    def fail(slug: str, number: int, token: str) -> dict[str, object]:
        raise GitHubError("offline")

    monkeypatch.setattr(command, "read_pull_request", fail)
    assert command.main(["jl-cmd/claude-dev-env", "1901"]) == 2


def test_parent_number_reads_both_spellings_and_ignores_other_values() -> None:
    assert command.followup_parent_number("FOLLOWUP to #1731.") == 1731
    assert command.followup_parent_number("Follow-up to #17310") == 17310
    assert command.followup_parent_number(None) is None
