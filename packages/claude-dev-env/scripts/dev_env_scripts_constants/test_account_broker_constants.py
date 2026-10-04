"""Tests for account broker constants and time helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dev_env_scripts_constants import account_broker_constants as broker_constants


def test_codex_usage_limit_signatures_loads_classifier_markers() -> None:
    signatures = broker_constants.codex_usage_limit_signatures()

    assert "rate limit" in signatures
    assert "http 429" in signatures


def test_utc_time_text_converts_an_offset_timestamp() -> None:
    moment = datetime(2026, 10, 3, 7, 30, tzinfo=timezone(timedelta(hours=-4)))

    assert broker_constants.utc_time_text(moment) == "2026-10-03T11:30:00+00:00"
    assert broker_constants.utc_time_text(None) is None


@pytest.mark.parametrize("timestamp", (None, 123, "not a timestamp", "2026-10-03T11:30:00"))
def test_parse_utc_time_rejects_values_without_a_timezone(timestamp: object) -> None:
    assert broker_constants.parse_utc_time(timestamp) is None


def test_parse_utc_time_converts_an_offset_timestamp() -> None:
    parsed = broker_constants.parse_utc_time("2026-10-03T07:30:00-04:00")

    assert parsed is not None
    assert parsed.isoformat() == "2026-10-03T11:30:00+00:00"
