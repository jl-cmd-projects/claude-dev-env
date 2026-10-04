"""Tests for the shared fixtures in hooks/conftest.py."""

from __future__ import annotations

import os
import subprocess
import sys

from hooks_constants.harness_scratchpad_constants import (
    CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME,
)


def test_live_session_id_is_absent_inside_each_test() -> None:
    assert CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME not in os.environ


def test_hook_subprocess_inherits_no_live_session_id() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import os; print(os.environ.get('{CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME}', ''))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == ""
