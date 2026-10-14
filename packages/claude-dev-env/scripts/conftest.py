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
import subprocess
import sys
from collections.abc import Callable
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

@pytest.fixture(autouse=True)
def isolated_broker_state_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the home directory at a per-test folder.

    ``broker_state_path`` builds its path from ``Path.home()``, which reads
    ``HOME`` on POSIX and ``USERPROFILE`` on Windows. Redirecting both keeps
    every bound copy of the resolver, and every other home-derived path, off
    the user's home directory.

    Returns:
        The isolated broker state path for this test.
    """
    isolated_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("USERPROFILE", str(isolated_home))
    return importlib.import_module("account_broker_support").broker_state_path()


def _link_directory(*, from_link: Path, to_target: Path) -> None:
    try:
        importlib.import_module("claude_account_profile")._link_directory(to_target, from_link)
    except subprocess.CalledProcessError as error:
        link_output = (error.stderr or error.stdout or b"").decode(errors="replace").strip()
        pytest.fail(f"directory link {from_link} -> {to_target} failed: {link_output}")
    except OSError as error:
        pytest.fail(f"directory link {from_link} -> {to_target} failed: {error}")


@pytest.fixture
def create_directory_link() -> Callable[..., None]:
    """Return a helper that points a new directory link at a target folder.

    Windows gets a junction, which needs no extra rights. Other systems get a
    symlink. A link that cannot be made fails the test on either system.

    Returns:
        The helper, called as ``create_directory_link(from_link=..., to_target=...)``.
    """
    return _link_directory
