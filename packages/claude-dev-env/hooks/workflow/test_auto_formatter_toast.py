"""The auto_formatter hook leaves the desktop alone after a format.

An install from before the package dropped ``hooks/notification`` keeps
``notification_utils.py`` on disk. These tests put a recording stand-in for
that module on the import path and check the hook never reads it.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOK_SCRIPT_PATH = Path(__file__).resolve().parent / "auto_formatter.py"


def _load_auto_formatter_module() -> ModuleType:
    module_spec = importlib.util.spec_from_file_location(
        "auto_formatter_toast_under_test", HOOK_SCRIPT_PATH
    )
    assert module_spec is not None and module_spec.loader is not None
    auto_formatter_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(auto_formatter_module)
    return auto_formatter_module


def _build_recording_notification_module(all_touched_names: list[str]) -> ModuleType:
    class RecordingNotificationModule(ModuleType):
        def __getattr__(self, attribute_name: str) -> object:
            if not attribute_name.startswith("__"):
                all_touched_names.append(attribute_name)
            return lambda *_arguments, **_options: False

    return RecordingNotificationModule("notification_utils")


def test_successful_format_opens_no_desktop_toast(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale notification_utils on the import path stays untouched after a format.

    ::

        ~/.claude/hooks/notification/notification_utils.py   left behind by an old install
        ruff format module.py  ->  exit 0
        ok:   nothing reads notification_utils
        flag: notify_windows() opens a toast window at the bottom of the screen
    """
    auto_formatter_module = _load_auto_formatter_module()
    all_touched_names: list[str] = []
    monkeypatch.setitem(
        sys.modules,
        "notification_utils",
        _build_recording_notification_module(all_touched_names),
    )

    def report_formatter_success(
        command: list[str], _file_path: str, _timeout_seconds: int
    ) -> tuple[subprocess.CompletedProcess[str], bool]:
        return subprocess.CompletedProcess(command, 0, "", ""), False

    monkeypatch.setattr(auto_formatter_module, "_run_command", report_formatter_success)

    auto_formatter_module.run_eligible_formatter("formatted_module.py")
    auto_formatter_module._run_prettier("formatted_module.js")

    assert all_touched_names == []
