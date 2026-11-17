"""Prove the cloud session shim reaches the packaged check with no installed package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIRECTORY = _PACKAGE_ROOT / "scripts"
_PACKAGED_CHECK_PATH = _PACKAGE_ROOT / "hooks" / "hooks_constants" / "cloud_session.py"
_CLOUD_SESSION_VARIABLE = "CLAUDE_CODE_REMOTE"
_IMPORT_PROBE_SOURCE = "\n".join(
    (
        "import json",
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        "head_before_import = sys.path[0]",
        "import cloud_session_access as shim",
        "print(json.dumps({",
        "    'check_path': sys.modules[shim.is_cloud_session.__module__].__file__,",
        "    'is_cloud_session': shim.is_cloud_session(),",
        "    'is_head_kept': sys.path[0] == head_before_import,",
        "}))",
    )
)


def _import_probe_results(marker_text: str | None) -> dict[str, object]:
    child_environment = {
        each_name: each_text for each_name, each_text in os.environ.items() if each_name != _CLOUD_SESSION_VARIABLE
    }
    if marker_text is not None:
        child_environment[_CLOUD_SESSION_VARIABLE] = marker_text
    completed_process = subprocess.run(
        [sys.executable, "-S", "-E", "-c", _IMPORT_PROBE_SOURCE, str(_SCRIPTS_DIRECTORY)],
        cwd=str(_PACKAGE_ROOT),
        env=child_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed_process.returncode == 0, completed_process.stderr
    return json.loads(completed_process.stdout)


def test_shim_resolves_the_packaged_check_without_an_installed_package() -> None:
    all_probe_results = _import_probe_results(None)

    assert Path(str(all_probe_results["check_path"])) == _PACKAGED_CHECK_PATH
    assert all_probe_results["is_head_kept"]


@pytest.mark.parametrize(
    ("marker_text", "is_expected_cloud"),
    [(None, False), ("", False), ("false", False), ("true", True), (" TRUE ", True)],
)
def test_shim_reports_a_cloud_session_from_the_marker(marker_text: str | None, is_expected_cloud: bool) -> None:
    assert _import_probe_results(marker_text)["is_cloud_session"] is is_expected_cloud
