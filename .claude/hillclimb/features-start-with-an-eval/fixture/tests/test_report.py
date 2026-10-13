"""Behavior tests for completed job reports."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

fixture_directory = str(Path(__file__).resolve().parents[1])
if fixture_directory not in sys.path:
    sys.path.insert(0, fixture_directory)

from jobs.report import finished_jobs


def test_finished_jobs_filters_and_sorts_by_finish_time(tmp_path: Path) -> None:
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

    assert [name for name, _, _ in finished_jobs(jobs_file, 7)] == ["early", "late"]
