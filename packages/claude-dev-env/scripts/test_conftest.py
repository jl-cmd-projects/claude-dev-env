import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import account_broker_support
from dev_env_scripts_constants.account_broker_constants import ALL_ACCOUNT_ENVIRONMENT_VARIABLES


@pytest.fixture(scope="module")
def exported_account_variables(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    exported_root = tmp_path_factory.mktemp("exported-overrides")
    with pytest.MonkeyPatch.context() as module_monkeypatch:
        for each_account_variable in ALL_ACCOUNT_ENVIRONMENT_VARIABLES:
            module_monkeypatch.setenv(each_account_variable, str(exported_root / each_account_variable))
        yield


def test_broker_state_path_follows_the_redirected_home(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert Path.home() == isolated_home
    assert account_broker_support.broker_state_path().is_relative_to(isolated_home)
    moved_home = tmp_path / "moved-home"
    monkeypatch.setenv("HOME", str(moved_home))
    monkeypatch.setenv("USERPROFILE", str(moved_home))
    assert account_broker_support.broker_state_path().is_relative_to(moved_home)


def test_isolated_home_clears_the_exported_account_variables(
    exported_account_variables: None, isolated_home: Path
) -> None:
    for each_account_variable in ALL_ACCOUNT_ENVIRONMENT_VARIABLES:
        assert each_account_variable not in os.environ


def test_isolated_home_keeps_the_python_user_base_for_a_new_interpreter(
    isolated_home: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import site; print(site.getuserbase())"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    child_user_base = Path(completed.stdout.strip())
    assert str(child_user_base) == os.environ["PYTHONUSERBASE"]
    assert child_user_base != isolated_home
    assert isolated_home not in child_user_base.parents
