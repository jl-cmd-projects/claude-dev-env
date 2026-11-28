"""Behavior tests for the late checkout markers of the nested hooks forwarder."""

from __future__ import annotations

import pathlib

import pytest

from lifecycle import nested_project_hooks_catch_up


def test_should_take_over_a_stale_claim_once_when_two_events_see_it_stale(
    tmp_path: pathlib.Path,
) -> None:
    claim_path = tmp_path / "beta.claimed"
    claim_path.write_text("1", encoding="utf-8")
    stale_generation = claim_path.stat().st_mtime_ns

    first_takeover = nested_project_hooks_catch_up._take_over(claim_path, stale_generation)
    second_takeover = nested_project_hooks_catch_up._take_over(claim_path, stale_generation)

    assert (first_takeover, second_takeover) == (True, False)
    assert claim_path.exists()


def test_should_mark_a_checkout_reported_and_done_only_when_asked(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    payload = {"session_id": "session-mark"}
    state_directory = nested_project_hooks_catch_up.session_state_directory("session-mark")

    nested_project_hooks_catch_up.mark_reported(payload, (tmp_path / "alpha",))
    nested_project_hooks_catch_up.mark_reported(payload, (tmp_path / "beta",), mark_done=True)

    assert sorted(each.name for each in state_directory.iterdir()) == [
        "alpha.reported",
        "beta.done",
        "beta.reported",
    ]


def test_should_report_nothing_for_a_session_id_that_names_a_path(
    tmp_path: pathlib.Path,
) -> None:
    report = nested_project_hooks_catch_up.start_late_checkouts(
        tmp_path, {"session_id": "../escape", "hook_event_name": "PreToolUse"}
    )

    assert report == nested_project_hooks_catch_up.CatchUpReport("", ())
