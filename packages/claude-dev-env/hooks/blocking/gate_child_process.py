"""Start, hold and stop the child processes the gate reads from.

::

    started_child(["git", "status"])   -> a child with its output piped
    job_holding(child)                 -> its Windows job, or None on POSIX
    stop_child(child, job)             -> the child and every process it started end
    close_job(job)                     -> the job handle closes

A stopped child gets a short grace to close its pipes, so a grandchild
that holds the output pipe cannot hold the gate.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.gate_run_reads_constants import (
    ALL_WINDOWS_TREE_KILL_WORDS,
    CLOSE_HANDLE_CALL,
    KERNEL32_LIBRARY_NAME,
    KILL_GRACE_SECONDS,
    PROCESS_HANDLE_ATTRIBUTE,
    STOPPED_JOB_EXIT_CODE,
    TERMINATE_JOB_CALL,
    WINDOWS_TREE_KILL_SECONDS,
)
from hooks_constants.subprocess_window import hidden_window_creation_flags


def started_child(
    all_command_words: Sequence[str],
    working_directory: str | None,
    all_environment_variables: Mapping[str, str] | None,
) -> subprocess.Popen[str] | None:
    """Start one read-only child with its output piped, or None when it cannot start.

    Args:
        all_command_words: The program and its arguments.
        working_directory: The directory the child runs in, or None for the gate's own.
        all_environment_variables: The child's whole environment, or None for the gate's own.
    """
    try:
        return subprocess.Popen(
            list(all_command_words),
            cwd=working_directory or None,
            env=dict(all_environment_variables) if all_environment_variables is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=sys.platform != "win32",
            creationflags=hidden_window_creation_flags(),
        )
    except OSError:
        return None


def _drain_within(child: subprocess.Popen[str], grace_seconds: float) -> None:
    try:
        child.communicate(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        return


def _kernel32() -> Any:
    if sys.platform != "win32":
        raise OSError("kernel32 exists only on Windows")
    kernel32 = ctypes.WinDLL(KERNEL32_LIBRARY_NAME, use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    return kernel32


def job_holding(child: subprocess.Popen[str]) -> int | None:
    """Put the child in a new Windows job object and return the job, or None.

    ::

        POSIX                         -> None
        Windows, the job is made      -> the job handle
        Windows, the job call fails   -> None

    Args:
        child: The child ``started_child`` gave.
    """
    if sys.platform != "win32":
        return None
    try:
        kernel32 = _kernel32()
        job = kernel32.CreateJobObjectW(None, None)
        if job and kernel32.AssignProcessToJobObject(job, int(getattr(child, PROCESS_HANDLE_ATTRIBUTE))):
            return int(job)
        if job:
            kernel32.CloseHandle(job)
    except (OSError, AttributeError, TypeError, ValueError, ctypes.ArgumentError):
        return None
    return None


def close_job(job: int | None) -> bool:
    """Close the job handle, and return whether the close succeeded.

    ::

        None                -> False, nothing to close
        a job handle        -> True once Windows closes it

    Args:
        job: The job handle ``job_holding`` gave, or None.
    """
    return _job_call_succeeded(job, CLOSE_HANDLE_CALL)


def _job_call_succeeded(job: int | None, call_name: str, *all_arguments: int) -> bool:
    if job is None:
        return False
    try:
        return bool(getattr(_kernel32(), call_name)(job, *all_arguments))
    except (OSError, AttributeError, TypeError, ValueError, ctypes.ArgumentError):
        return False


def _stop_windows_tree(child: subprocess.Popen[str], job: int | None) -> None:
    if not _job_call_succeeded(job, TERMINATE_JOB_CALL, STOPPED_JOB_EXIT_CODE):
        _run_taskkill(child)
    if child.poll() is None:
        child.kill()
    _drain_within(child, KILL_GRACE_SECONDS - WINDOWS_TREE_KILL_SECONDS)


def _run_taskkill(child: subprocess.Popen[str]) -> None:
    try:
        subprocess.run(
            [*ALL_WINDOWS_TREE_KILL_WORDS, str(child.pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=WINDOWS_TREE_KILL_SECONDS,
            creationflags=hidden_window_creation_flags(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return


def stop_child(child: subprocess.Popen[str], job: int | None) -> None:
    """End the child and every process it started, inside ``KILL_GRACE_SECONDS`` in all.

    ::

        POSIX     the child leads its own process group  -> SIGKILL to the group, then the pipe grace
        Windows   the child's job object                 -> end the job, then the pipe grace
        Windows   no job could be made                   -> bounded hidden taskkill /T /F, then the pipe grace

    A grandchild that holds the output pipe dies with the child, so the pipe
    closes, even when the child itself already exited. Should one escape, the
    grace still ends the wait.

    Args:
        child: The child to stop.
        job: The job handle ``job_holding`` gave, or None.
    """
    if sys.platform == "win32":
        _stop_windows_tree(child, job)
        return
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except OSError:
        child.kill()
    _drain_within(child, KILL_GRACE_SECONDS)
