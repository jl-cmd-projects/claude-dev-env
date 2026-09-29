import runpy
import sys
from pathlib import Path

import pytest


def test_conftest_adds_routing_and_hooks_to_module_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing_directory = Path(__file__).resolve().parent
    hooks_directory = routing_directory.parent
    expected_paths = [str(hooks_directory), str(routing_directory)]
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path not in expected_paths])

    runpy.run_path(str(routing_directory / "conftest.py"))

    assert sys.path[:2] == expected_paths
