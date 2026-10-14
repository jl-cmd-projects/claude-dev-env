"""Shared fixtures for the usage-wrapup tests."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def run_from_repository_root() -> Callable[
    [list[str]], subprocess.CompletedProcess[str]
]:
    """Return a runner that executes a command from the repository root and asserts it exits 0."""

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        completed_run = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            shell=os.name == "nt",
        )
        assert completed_run.returncode == 0, completed_run.stderr
        return completed_run

    return run
