"""Behavior tests for completed job reports."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobs import report
from jobs.report import finished_jobs

FROZEN_NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return FROZEN_NOW


def _write_jobs(jobs_file: Path, finished_at_by_name: dict[str, datetime]) -> None:
    jobs_file.write_text(
        json.dumps(
            [
                {
                    "name": each_name,
                    "status": "done",
                    "finished_at": each_finish.isoformat(),
                }
                for each_name, each_finish in finished_at_by_name.items()
            ]
        )
    )


def test_finished_jobs_keeps_every_status_inside_the_range_oldest_first(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(
        json.dumps(
            [
                {
                    "name": "old",
                    "status": "done",
                    "finished_at": (now - timedelta(days=8)).isoformat(),
                },
                {
                    "name": "late",
                    "status": "done",
                    "finished_at": (now - timedelta(days=1)).isoformat(),
                },
                {
                    "name": "early",
                    "status": "failed",
                    "finished_at": (now - timedelta(days=2)).isoformat(),
                },
            ]
        )
    )

    assert [
        (name, status) for name, status, _ in finished_jobs(jobs_file, 7)
    ] == [("early", "failed"), ("late", "done")]


def test_finished_jobs_includes_a_job_finished_at_the_range_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report, "datetime", _FrozenDatetime)
    jobs_file = tmp_path / "jobs.json"
    range_start = FROZEN_NOW - timedelta(days=7)
    _write_jobs(
        jobs_file,
        {
            "on-start": range_start,
            "before-start": range_start - timedelta(seconds=1),
        },
    )

    assert [name for name, _, _ in finished_jobs(jobs_file, 7)] == ["on-start"]
