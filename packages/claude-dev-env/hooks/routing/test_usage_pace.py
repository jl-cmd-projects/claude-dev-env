import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from usage_pace import (
    UsageUnreadable,
    build_verdict,
    measure_account_pace,
    measure_window_pace,
)

USAGE_PACE_SCRIPT = Path(__file__).resolve().parent / "usage_pace.py"
NOW = datetime(2026, 9, 29, 13, 57, 40, tzinfo=timezone.utc)
FIVE_HOUR_RESET = "2026-09-29T18:50:00+00:00"
WEEKLY_RESET = "2026-10-03T20:00:00+00:00"


def _payload(five_hour_used: float, weekly_used: float) -> dict[str, object]:
    return {
        "five_hour": {"utilization": five_hour_used, "resets_at": FIVE_HOUR_RESET},
        "seven_day": {"utilization": weekly_used, "resets_at": WEEKLY_RESET},
        "seven_day_opus": None,
    }


def _run_script(tmp_path: Path, payload: object) -> tuple[int, dict[str, object]]:
    payload_path = tmp_path / "usage.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(USAGE_PACE_SCRIPT),
            "--payload-file",
            str(payload_path),
            "--now",
            NOW.isoformat(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_should_flag_a_window_whose_spend_runs_ahead_of_the_clock() -> None:
    pace = measure_window_pace(
        "five_hour",
        timedelta(hours=5),
        {"utilization": 3.0, "resets_at": FIVE_HOUR_RESET},
        NOW,
    )
    assert pace.elapsed_percent == 2.6
    assert pace.over_pace is True


def test_should_clear_a_window_whose_spend_trails_the_clock() -> None:
    pace = measure_window_pace(
        "seven_day",
        timedelta(days=7),
        {"utilization": 20.0, "resets_at": WEEKLY_RESET},
        NOW,
    )
    assert pace.elapsed_percent == 39.3
    assert pace.over_pace is False


def test_should_clamp_elapsed_time_to_the_window_length() -> None:
    long_past_reset = measure_window_pace(
        "five_hour",
        timedelta(hours=5),
        {"utilization": 99.0, "resets_at": "2026-09-29T10:00:00Z"},
        NOW,
    )
    assert long_past_reset.elapsed_percent == 100.0
    assert long_past_reset.over_pace is False


def test_should_report_over_pace_when_any_window_runs_ahead() -> None:
    verdict = build_verdict(measure_account_pace(_payload(1.0, 93.0), NOW), NOW)
    assert verdict["over_pace"] is True
    assert [each["over_pace"] for each in verdict["windows"]] == [False, True]


def test_should_report_under_pace_when_every_window_trails() -> None:
    verdict = build_verdict(measure_account_pace(_payload(1.0, 20.0), NOW), NOW)
    assert verdict["over_pace"] is False


@pytest.mark.parametrize(
    "broken_payload",
    [
        {"seven_day": {"utilization": 20.0, "resets_at": WEEKLY_RESET}},
        {
            "five_hour": {"utilization": None, "resets_at": FIVE_HOUR_RESET},
            "seven_day": {"utilization": 1.0, "resets_at": WEEKLY_RESET},
        },
        {
            "five_hour": {"utilization": 1.0, "resets_at": "soon"},
            "seven_day": {"utilization": 1.0, "resets_at": WEEKLY_RESET},
        },
    ],
)
def test_should_treat_a_missing_or_unreadable_window_as_unreadable(
    broken_payload: dict[str, object],
) -> None:
    with pytest.raises(UsageUnreadable):
        measure_account_pace(broken_payload, NOW)


def test_should_exit_zero_with_the_verdict_when_over_pace(tmp_path: Path) -> None:
    exit_code, verdict = _run_script(tmp_path, _payload(3.0, 93.0))
    assert exit_code == 0
    assert verdict["over_pace"] is True


def test_should_exit_one_when_under_pace(tmp_path: Path) -> None:
    exit_code, verdict = _run_script(tmp_path, _payload(1.0, 20.0))
    assert exit_code == 1
    assert verdict["over_pace"] is False


def test_should_exit_two_with_a_null_verdict_when_unreadable(tmp_path: Path) -> None:
    exit_code, verdict = _run_script(tmp_path, {"five_hour": None})
    assert exit_code == 2
    assert verdict["over_pace"] is None
    assert verdict["error"] == "usage response has no five_hour window"
