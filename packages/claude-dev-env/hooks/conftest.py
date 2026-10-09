"""Shared pytest fixtures for the hooks/ suite, visible under blocking/ and validators/."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_HOOKS_DIRECTORY = Path(__file__).resolve().parent
_BLOCKING_DIRECTORY = _HOOKS_DIRECTORY / "blocking"
for each_directory in (_HOOKS_DIRECTORY, _BLOCKING_DIRECTORY):
    if str(each_directory) not in sys.path:
        sys.path.insert(0, str(each_directory))

_is_ephemeral_script_path = importlib.import_module("code_rules_shared").is_ephemeral_script_path
_EPHEMERAL_EXEMPT_DISABLE_ENVIRONMENT_VARIABLE_NAME = importlib.import_module(
    "hooks_constants.code_rules_enforcer_constants"
).EPHEMERAL_EXEMPT_DISABLE_ENVIRONMENT_VARIABLE_NAME
_CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME = importlib.import_module(
    "hooks_constants.harness_scratchpad_constants"
).CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME

_CLOUD_SESSION_ENVIRONMENT_VARIABLE_NAME = importlib.import_module(
    "hooks_constants.headless_claude_broker_gate_constants"
).CLOUD_SESSION_ENV_VAR

_ROOT_ANCHORED_PROBE_PATH = "/tmp/scratch.py"


@pytest.fixture(autouse=True)
def isolate_from_live_session_scratchpad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the live harness session id before each hooks test.

    A Claude Code session exports ``CLAUDE_CODE_SESSION_ID``. When this checkout
    sits inside that session's scratchpad, the scratchpad predicate classifies
    every repository file as throwaway scratch, and the gates under test step
    aside. Tests that exercise the scratchpad match set their own session id.

    Args:
        monkeypatch: Pytest's environment-variable patcher, torn down after the test.
    """
    monkeypatch.delenv(_CLAUDE_SESSION_ID_ENVIRONMENT_VARIABLE_NAME, raising=False)


@pytest.fixture(autouse=True)
def isolate_from_live_cloud_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the cloud session marker before each hooks test.

    A Claude Code cloud session exports CLAUDE_CODE_REMOTE=true, and gates
    that stand aside in cloud would then pass every case. Tests that exercise the
    cloud path set the variable themselves.

    Args:
        monkeypatch: Pytest's environment-variable patcher, torn down after the test.
    """
    monkeypatch.delenv(_CLOUD_SESSION_ENVIRONMENT_VARIABLE_NAME, raising=False)


@pytest.fixture
def ephemeral_exempt_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn off the ephemeral scratch-path exemption for the current test.

    Sets ``CLAUDE_CODE_RULES_DISABLE_EPHEMERAL_EXEMPT`` so a gate under test
    judges the test's own scratch targets for real, rather than stepping aside
    because they sit under a temp root.

    The probe path is root-anchored ``/tmp``, which the classifier treats as
    ephemeral on every platform, so the assert fails on any change that stops
    reading the disable flag. A probe on the shared OS temp root would pass on
    Windows whether the flag is read or not, since the classifier already
    excludes that root by design.

    Args:
        monkeypatch: Pytest's environment-variable patcher, torn down after the test.
    """
    monkeypatch.setenv(_EPHEMERAL_EXEMPT_DISABLE_ENVIRONMENT_VARIABLE_NAME, "1")
    assert _is_ephemeral_script_path(_ROOT_ANCHORED_PROBE_PATH) is False, (
        "ephemeral_exempt_off must turn off the scratch-path exemption; a change "
        "that stops reading the disable flag must fail here, not silently return "
        "every test in the file to deciding nothing"
    )
