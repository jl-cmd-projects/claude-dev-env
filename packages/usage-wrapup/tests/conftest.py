"""Shared fixtures for the usage-wrapup tests."""

import shutil

import pytest


@pytest.fixture
def require_bun() -> None:
    """Skip the test when bun is not on PATH."""
    if shutil.which("bun") is None:
        pytest.skip("bun is not installed")
