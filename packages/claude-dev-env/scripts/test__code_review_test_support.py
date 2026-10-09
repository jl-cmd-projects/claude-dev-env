from __future__ import annotations

from pathlib import Path

import pytest

import _code_review_test_support as support
from dev_env_scripts_constants.account_broker_constants import Product


def test_should_build_served_and_exhausted_outcomes() -> None:
    served = support.claude_served(returncode=4, stdout="failed")
    exhausted = support.claude_failed()

    assert served.returncode == 4
    assert served.stdout == "failed"
    assert served.status == "advisor_blocked"
    assert served.attempts == (("claude", "served"),)
    assert exhausted.returncode == support.WAIT_EXIT_CODE
    assert exhausted.status == "exhausted"
    assert exhausted.attempts == (("claude", "usage_limited"),)


def test_should_record_runner_options_from_installed_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_outcome = support.claude_served()
    call_log = support.install_seams(
        monkeypatch, claude_outcome=expected_outcome
    )

    outcome = support.invoker.review_claude_runner(
        Product.CLAUDE, ["claude", "-p"], stdin_text="", cwd=tmp_path
    )

    assert outcome is expected_outcome
    assert call_log.claude_calls == 1
    assert call_log.claude_arguments == ["-p"]
    assert call_log.is_stdin_empty is True
    assert call_log.claude_working_directory == tmp_path
