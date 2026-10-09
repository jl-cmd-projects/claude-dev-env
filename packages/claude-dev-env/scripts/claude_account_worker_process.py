"""Time one broker job for the headless Claude worker."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from dev_env_scripts_constants.account_broker_constants import JobOutcome, Product
from dev_env_scripts_constants.claude_account_worker_constants import SECONDS_PER_MINUTE


def invoke_worker(
    *,
    all_arguments: list[str],
    cwd: Path,
    prompt_text: str,
    timeout_minutes: int,
    runner: Callable[..., JobOutcome],
    live_log: Path | None = None,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> tuple[JobOutcome, float]:
    """Run one broker job and measure its elapsed time.

    Args:
        all_arguments: Claude command-line arguments passed to the runner.
        cwd: Working directory for the job.
        prompt_text: Text the runner writes to the job's standard input.
        timeout_minutes: Job time limit in minutes; the runner receives it in seconds.
        runner: Broker job runner, called with ``Product.CLAUDE``,
            ``encoding="utf-8"``, and ``errors="replace"``.
        live_log: File the runner writes the job's standard output into as it
            runs, passed only when set.
        monotonic_clock: Clock read once before and once after the job.

    Returns:
        The runner's job outcome and the difference between the two clock reads.
    """
    started_at = monotonic_clock()
    all_log_options = {} if live_log is None else {"live_log": live_log}
    outcome = runner(
        Product.CLAUDE,
        all_arguments,
        timeout_seconds=timeout_minutes * SECONDS_PER_MINUTE,
        stdin_text=prompt_text,
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
        **all_log_options,
    )
    return outcome, monotonic_clock() - started_at
