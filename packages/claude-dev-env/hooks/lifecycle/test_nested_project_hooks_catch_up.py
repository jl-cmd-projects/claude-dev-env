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


def test_should_mark_a_checkout_reported_without_marking_it_done(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    payload = {"session_id": "session-mark"}
    state_directory = nested_project_hooks_catch_up.session_state_directory("session-mark")

    nested_project_hooks_catch_up.mark_reported(payload, (tmp_path / "alpha",))

    assert sorted(each.name for each in state_directory.iterdir()) == ["alpha.reported"]


def test_should_report_nothing_for_a_session_id_that_names_a_path(
    tmp_path: pathlib.Path,
) -> None:
    report = nested_project_hooks_catch_up.start_late_checkouts(
        tmp_path, {"session_id": "../escape", "hook_event_name": "PreToolUse"}
    )

    assert report == nested_project_hooks_catch_up.CatchUpReport("", ())


@pytest.mark.parametrize(
    ("source", "all_expected_markers"),
    [
        ("startup", ["alpha.done", "alpha.reported"]),
        ("compact", []),
    ],
)
def test_should_mark_checkouts_done_only_at_a_startup_session_start(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    all_expected_markers: list[str],
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    session_directory = tmp_path / "session"
    (session_directory / "alpha" / ".git").mkdir(parents=True)
    (session_directory / "alpha" / ".claude").mkdir()
    (session_directory / "alpha" / ".claude" / "settings.json").write_text(
        '{"hooks": {}}', encoding="utf-8"
    )
    payload = {"session_id": "session-start", "hook_event_name": "SessionStart", "source": source}

    report = nested_project_hooks_catch_up.start_late_checkouts(session_directory, payload)

    state_directory = nested_project_hooks_catch_up.session_state_directory("session-start")
    all_markers = (
        sorted(each.name for each in state_directory.glob("*")) if state_directory.exists() else []
    )
    assert report == nested_project_hooks_catch_up.CatchUpReport("", ())
    assert all_markers == all_expected_markers
