from datetime import timedelta

from hooks_constants.usage_pace_constants import ALL_RATE_WINDOW_LENGTHS


def test_usage_pace_windows_have_expected_lengths() -> None:
    assert dict(ALL_RATE_WINDOW_LENGTHS) == {
        "five_hour": timedelta(hours=5),
        "seven_day": timedelta(days=7),
    }
