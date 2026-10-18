"""Tests for the shared check that tells a hook it runs in a Claude Code cloud session."""

from __future__ import annotations

import pytest

from hooks_constants.cloud_session import is_cloud_session


@pytest.mark.parametrize("marker_value", ["true", "TRUE", " true "])
def test_should_read_the_cloud_marker_case_and_space_blind(
    monkeypatch: pytest.MonkeyPatch, marker_value: str
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", marker_value)
    assert is_cloud_session() is True


@pytest.mark.parametrize("marker_value", ["false", "", "1"])
def test_should_not_treat_another_marker_value_as_cloud(
    monkeypatch: pytest.MonkeyPatch, marker_value: str
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", marker_value)
    assert is_cloud_session() is False


def test_should_not_report_cloud_when_the_marker_is_unset() -> None:
    assert is_cloud_session() is False
