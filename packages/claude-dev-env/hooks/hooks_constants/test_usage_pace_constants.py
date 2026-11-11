from datetime import timedelta

from hooks_constants.usage_pace_constants import (
    ALL_OPTIONAL_WINDOW_NAMES,
    ALL_RATE_WINDOW_LENGTHS,
)


def test_usage_pace_windows_have_expected_lengths() -> None:
    assert dict(ALL_RATE_WINDOW_LENGTHS) == {
        "five_hour": timedelta(hours=5),
        "seven_day": timedelta(days=7),
    }


def test_usage_pace_treats_only_the_five_hour_window_as_optional() -> None:
    assert ALL_OPTIONAL_WINDOW_NAMES == {"five_hour"}
