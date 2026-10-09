"""Report the jobs that finished inside a date range."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_row(row: dict[str, str]) -> tuple[str, str, datetime]:
    """Return a job row's name, status and finish time.

    Args:
        row: One job entry from jobs.json.

    Returns:
        The name, the status and the finish time in UTC.
    """
    return row["name"], row["status"], datetime.fromisoformat(row["finished_at"])


def finished_jobs(jobs_file: Path, days: int) -> list[tuple[str, str, datetime]]:
    """Return the jobs that finished in the last given number of days, oldest first.

    Args:
        jobs_file: The jobs.json file.
        days: How many days back the range starts.

    Returns:
        One parsed row per finished job inside the range.
    """
    range_start = datetime.now(timezone.utc) - timedelta(days=days)
    all_rows = [parse_row(each_row) for each_row in json.loads(jobs_file.read_text())]
    return sorted(
        (each_row for each_row in all_rows if each_row[2] >= range_start),
        key=lambda each_row: each_row[2],
    )
