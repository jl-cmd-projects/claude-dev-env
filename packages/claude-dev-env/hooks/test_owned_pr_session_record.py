"""Behavior tests for the owned pull request session record."""

from __future__ import annotations

from pathlib import Path

import pytest

import owned_pr_session_record

SESSION_ID = "session-abc"
PULL_REQUEST = {
    "owner": "jl-cmd",
    "repository": "snake-game",
    "number": "9",
    "url": "https://github.com/jl-cmd/snake-game/pull/9",
}


@pytest.fixture(autouse=True)
def isolated_temp_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(owned_pr_session_record.tempfile, "gettempdir", lambda: str(tmp_path))


def test_session_record_path_should_name_the_session_in_the_temp_folder(tmp_path: Path) -> None:
    assert (
        owned_pr_session_record.session_record_path("a/b c") == tmp_path / "owned-pr-loop-abc.json"
    )


def test_record_pull_request_should_keep_one_entry_per_url() -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    assert owned_pr_session_record.all_recorded_pull_requests(SESSION_ID) == [PULL_REQUEST]


def test_record_pull_request_should_skip_a_payload_without_a_session_id(tmp_path: Path) -> None:
    owned_pr_session_record.record_pull_request(None, PULL_REQUEST)
    assert list(tmp_path.iterdir()) == []


def test_all_recorded_pull_requests_should_read_a_malformed_file_as_empty() -> None:
    owned_pr_session_record.session_record_path(SESSION_ID).write_text(
        "{not json", encoding="utf-8"
    )
    assert owned_pr_session_record.all_recorded_pull_requests(SESSION_ID) == []
