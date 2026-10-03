"""The mypy_validator hook reports a block through its reply and nothing else.

An install from before the package dropped ``hooks/notification`` keeps
``notification_utils.py`` on disk. This test puts a recording stand-in for
that module on the import path and checks a blocked write never reads it.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOK_PATH = Path(__file__).resolve().parent / "mypy_validator.py"
TYPE_ERROR_MODULE_SOURCE = 'value: int = "not an integer"\n'


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mypy_validator_toast_under_test", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_recording_notification_module(all_touched_names: list[str]) -> ModuleType:
    class RecordingNotificationModule(ModuleType):
        def __getattr__(self, attribute_name: str) -> object:
            if not attribute_name.startswith("__"):
                all_touched_names.append(attribute_name)
            return lambda *_arguments, **_options: False

    return RecordingNotificationModule("notification_utils")


def test_type_error_block_opens_no_desktop_toast(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A blocked write reports through the hook reply and leaves the desktop alone.

    ::

        mypy typed_module.py  ->  error: Incompatible types
        ok:   {"decision": "block"} on stdout, notification_utils untouched
        flag: notify_windows() opens a toast window at the bottom of the screen
    """
    validator = _load_validator()
    project_root = tmp_path_factory.mktemp("blocked_project")
    target_file = project_root / "typed_module.py"
    target_file.write_text(TYPE_ERROR_MODULE_SOURCE, encoding="utf-8")
    all_touched_names: list[str] = []
    monkeypatch.setitem(
        sys.modules,
        "notification_utils",
        _build_recording_notification_module(all_touched_names),
    )
    monkeypatch.setattr(validator, "discover_project_root", lambda _target: project_root)
    monkeypatch.setattr(
        validator,
        "run_mypy",
        lambda _target, _root: (1, f"{target_file}:1: error: Incompatible types\n"),
    )
    monkeypatch.setattr(validator, "log_hook_block", lambda **_details: None)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target_file)}}))
    )

    with pytest.raises(SystemExit):
        validator.main()

    assert json.loads(capsys.readouterr().out)["decision"] == "block"
    assert all_touched_names == []
