import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixture_overlay"))

from jobs.durations import format_duration


def test_format_duration_uses_hours_and_zero_padded_minutes() -> None:
    assert format_duration(2 * 60 * 60 + 5 * 60 + 59) == "2h 05m"
    assert format_duration(59) == "0h 00m"
