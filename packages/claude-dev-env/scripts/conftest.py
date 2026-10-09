"""Put the scripts and hooks directories on ``sys.path`` for every test here.

The code-review invoker and its constants package live beside these tests
rather than on the default pytest path, so each test module can import them
by bare name once this directory is registered. The hooks directory and its
session package are registered too, so a test imports ``followup_ledger``,
``hooks_constants``, or ``untracked_repo_detector`` by bare name.

::

    import invoke_code_review as invoker   # resolves here
    from dev_env_scripts_constants...      # resolves here

pytest loads this file before collecting sibling test modules, so the path
is in place by the time any test module runs its top-level imports.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_scripts_directory = Path(__file__).resolve().parent
_hooks_directory = _scripts_directory.parent / "hooks"
for each_import_directory in (
    _hooks_directory / "session",
    _hooks_directory,
    _scripts_directory,
):
    if str(each_import_directory) not in sys.path:
        sys.path.insert(0, str(each_import_directory))

_live_broker_state_resolver = importlib.import_module("account_broker_support").broker_state_path


@pytest.fixture(autouse=True)
def isolated_broker_state_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point every module's ``broker_state_path`` at a per-test file.

    ``account_broker`` binds ``broker_state_path`` by name from
    ``account_broker_support``, so each bound copy is replaced. A test that
    patches only one copy still keeps the other off the home directory.

    Returns:
        The isolated broker state path for this test.
    """
    isolated_path = tmp_path / "account-broker" / "state.json"
    for each_module in list(sys.modules.values()):
        if getattr(each_module, "broker_state_path", None) is _live_broker_state_resolver:
            monkeypatch.setattr(each_module, "broker_state_path", lambda: isolated_path)
    return isolated_path
