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
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> tuple[JobOutcome, float]:
    """Run one broker job and measure its elapsed time."""
    started_at = monotonic_clock()
    outcome = runner(
        Product.CLAUDE,
        all_arguments,
        timeout_seconds=timeout_minutes * SECONDS_PER_MINUTE,
        stdin_text=prompt_text,
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
    )
    return outcome, monotonic_clock() - started_at
