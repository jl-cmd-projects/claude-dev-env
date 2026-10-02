"""Specifications for the scheduled task Install-SweepEmptyDirs.ps1 registers.

A task that starts a console program straight from Task Scheduler draws a
console window on the signed-in desktop at every run. The registered action
starts the program through conhost.exe --headless so no window appears.
"""

from __future__ import annotations

import re
from pathlib import Path

_INSTALLER_PATH = Path(__file__).resolve().parents[1] / "Install-SweepEmptyDirs.ps1"
_UTF8_ENCODING = "utf-8"
_ACTION_PATTERN = re.compile(
    r"^\$Action = New-ScheduledTaskAction -Execute (\$\w+) -Argument (.+)$",
    re.MULTILINE,
)
_CONHOST_ASSIGNMENT = (
    "$ConhostPath = Join-Path -Path $env:SystemRoot -ChildPath 'System32\\conhost.exe'"
)


def _registered_action() -> tuple[str, str]:
    installer_text = _INSTALLER_PATH.read_text(encoding=_UTF8_ENCODING)
    all_actions = _ACTION_PATTERN.findall(installer_text)
    assert len(all_actions) == 1, all_actions
    return all_actions[0]


def test_should_start_the_task_through_conhost() -> None:
    installer_text = _INSTALLER_PATH.read_text(encoding=_UTF8_ENCODING)
    executable_variable, _ = _registered_action()

    assert executable_variable == "$ConhostPath"
    assert _CONHOST_ASSIGNMENT in installer_text


def test_should_pass_headless_before_the_python_program() -> None:
    _, argument_text = _registered_action()

    assert argument_text.startswith('"--headless ""$PythonPath"" ""$ScriptPath""')
