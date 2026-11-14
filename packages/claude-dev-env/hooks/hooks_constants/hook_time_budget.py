"""One time budget shared by every slow call a hook run makes.

The host kills a hook that outlives its registered timeout, and a killed hook
sends no signal. A hook opens a budget below that timeout for its run, and each
git, gh, network, or child call asks how long it may wait::

    with time_budget(50):
        call_timeout(10)  -> 10 while more than 10 seconds are left
        call_timeout(10)  -> 3.2 when 3.2 seconds are left
        call_timeout(10)  -> None once the budget is spent, so the call is skipped

Outside a budget, call_timeout returns the cap, so callers that never open a
budget keep their own timeouts. A nested budget never ends later than the one
around it. The budget resets when the block exits, so one run never leaks its
deadline into the next.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_run_deadline: ContextVar[float] = ContextVar("hook_run_deadline", default=math.inf)


@contextmanager
def time_budget(budget_seconds: float) -> Iterator[None]:
    """Bound every call_timeout inside the block to budget_seconds from now.

    Args:
        budget_seconds: How long the calls inside the block may take in total.
    """
    deadline = min(_run_deadline.get(), time.monotonic() + budget_seconds)
    reset_token = _run_deadline.set(deadline)
    try:
        yield
    finally:
        _run_deadline.reset(reset_token)


def remaining_seconds() -> float:
    """Return the seconds left in the open budget, or infinity outside one."""
    return _run_deadline.get() - time.monotonic()


def call_timeout(cap_seconds: float) -> float | None:
    """Return the timeout for the next call, or None when no time is left.

    Args:
        cap_seconds: The call's own timeout, used whole while the budget allows it.

    Returns:
        The smaller of cap_seconds and the time left, or None once the budget is spent.
    """
    time_left = remaining_seconds()
    if time_left <= 0:
        return None
    return min(cap_seconds, time_left)
