"""Behavior tests for the log cleanup."""

import os
import time
from pathlib import Path

from jobs.cleanup import remove_old_logs


def test_cleanup_should_delete_only_logs_past_the_cutoff(tmp_path: Path) -> None:
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    old_log.write_text("old")
    new_log.write_text("new")
    forty_days_ago = time.time() - 40 * 86400
    os.utime(old_log, (forty_days_ago, forty_days_ago))
    assert remove_old_logs(tmp_path, 30) == [old_log]
    assert new_log.exists()
