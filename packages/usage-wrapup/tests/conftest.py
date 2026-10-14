"""Shared fixtures for the usage-wrapup tests."""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 120


@pytest.fixture
def run_repository_command() -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    """Return a runner that executes a command from the repository root and asserts it exits 0."""

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        executable_path = shutil.which(command[0])
        assert executable_path is not None, f"{command[0]} is not on PATH"
        completed_run = subprocess.run(
            [executable_path, *command[1:]],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            encoding="utf-8",
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        assert (
            completed_run.returncode == 0
        ), f"{completed_run.stdout}\n{completed_run.stderr}"
        return completed_run

    return run
