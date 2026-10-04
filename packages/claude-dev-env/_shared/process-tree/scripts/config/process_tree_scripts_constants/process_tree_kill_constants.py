"""Named constants for ``process_tree_kill.py``.

Every caller that ends a child process and its descendants reads the taskkill
command, its flags, and the bound on the kill command from here rather than
embedding the values in its own module.
"""

from __future__ import annotations

WINDOWS_TASKKILL_COMMAND: str = "taskkill"
"""Windows command that ends a process by id."""

WINDOWS_TASKKILL_TREE_FLAG: str = "/T"
"""``taskkill`` flag that extends the kill to every descendant process."""

WINDOWS_TASKKILL_FORCE_FLAG: str = "/F"
"""``taskkill`` flag that forces termination rather than requesting it."""

WINDOWS_TASKKILL_PID_FLAG: str = "/PID"
"""``taskkill`` flag that names the target process id."""

PROCESS_TREE_KILL_TIMEOUT_SECONDS: int = 10
"""Seconds allowed for the tree-kill command itself before it is abandoned.

Gates the kill command alone. Each caller sets its own bound on the drain that
follows the kill.
"""

PROCESS_TREE_EXIT_WAIT_SECONDS: float = 2.0
"""Seconds ``terminate_process_tree`` waits for the signalled POSIX group to exit.

A SIGKILL takes effect when the kernel next schedules each target, so a
descendant can still run for a moment after ``killpg`` returns. The wait ends
as soon as no group member is still running; the bound applies only when a
member survived the signal.
"""

PROCESS_TREE_EXIT_POLL_SECONDS: float = 0.01
"""Pause between checks for running members of the signalled process group."""
