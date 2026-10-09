"""Delete job logs older than a cutoff."""

import time
from pathlib import Path

from jobs.config.constants import SECONDS_PER_DAY


def remove_old_logs(folder: Path, days: int) -> list[Path]:
    """Delete each log in the folder older than the given number of days.

    Args:
        folder: The folder that holds the job logs.
        days: The age in days past which a log is deleted.

    Returns:
        The paths that were deleted.
    """
    all_logs = sorted(
        folder.glob("*.log"), key=lambda each_log: each_log.stat().st_mtime
    )
    newest_time = max(each_log.stat().st_mtime for each_log in all_logs)
    cutoff = min(newest_time, time.time()) - days * SECONDS_PER_DAY
    all_removed = [
        each_log for each_log in all_logs if each_log.stat().st_mtime < cutoff
    ]
    for each_log in all_removed:
        each_log.unlink()
    return all_removed
