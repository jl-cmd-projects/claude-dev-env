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
import site
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

from dev_env_scripts_constants.account_broker_constants import ALL_ACCOUNT_ENVIRONMENT_VARIABLES


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the home directory at a per-test folder for every test here.

    ``Path.home()`` reads ``HOME`` on POSIX and ``USERPROFILE`` on Windows, so
    redirecting both keeps call-time home lookups, such as
    ``broker_state_path``, off the user's home directory. The variables in
    ``ALL_ACCOUNT_ENVIRONMENT_VARIABLES`` are cleared, so account roots fall
    back to the per-test home and no developer roster applies. A value built
    from ``Path.home()`` at import time keeps the user's home.
    ``PYTHONUSERBASE`` stays on the user base captured before the redirect, so
    a new interpreter still imports packages installed for this user.

    Returns:
        The per-test home directory.
    """
    user_base = site.getuserbase()
    isolated_home_directory = tmp_path / "home"
    monkeypatch.setenv("PYTHONUSERBASE", user_base)
    monkeypatch.setenv("HOME", str(isolated_home_directory))
    monkeypatch.setenv("USERPROFILE", str(isolated_home_directory))
    for each_account_variable in ALL_ACCOUNT_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(each_account_variable, raising=False)
    return isolated_home_directory


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
