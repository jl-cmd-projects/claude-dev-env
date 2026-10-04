"""Chain-invocation argv assembly, empty stdin, and working directory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import invoke_code_review as invoker
from _code_review_test_support import (
    FIXTURE_SESSION_OPUS,
    FIXTURE_SESSION_SONNET,
    HOST_PROFILE_THIRD_PARTY,
    claude_served,
    init_git_repository,
    install_seams,
    run_review,
)
from dev_env_scripts_constants.code_review_constants import (
    CODE_REVIEW_MODEL_ALIAS,
    DEFAULT_CODE_REVIEW_EFFORT,
    REVIEW_PERMISSION_MODE as PERMISSION_MODE_BYPASS,
    PERMISSION_MODE_FLAG,
)
from dev_env_scripts_constants.account_broker_constants import JobOutcome, WAIT_EXIT_CODE
from dev_env_scripts_constants.grok_worker_constants import (
    MODEL_FLAG,
    OUTPUT_FORMAT_FLAG,
    OUTPUT_FORMAT_JSON,
    SINGLE_TURN_FLAG,
)


def test_chain_argv_assembly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    working_directory = init_git_repository(tmp_path / "repo")
    call_log = install_seams(
        monkeypatch,
        host_profile=HOST_PROFILE_THIRD_PARTY,
        claude_outcome=claude_served(),
        working_directory=working_directory,
    )

    run_review(working_directory, session_model=FIXTURE_SESSION_SONNET)

    assert call_log.claude_arguments == [
        SINGLE_TURN_FLAG,
        invoker.build_code_review_prompt(DEFAULT_CODE_REVIEW_EFFORT),
        MODEL_FLAG,
        CODE_REVIEW_MODEL_ALIAS,
        OUTPUT_FORMAT_FLAG,
        OUTPUT_FORMAT_JSON,
        PERMISSION_MODE_FLAG,
        PERMISSION_MODE_BYPASS,
    ]


def test_chain_redirects_empty_stdin_and_sets_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    working_directory = init_git_repository(tmp_path / "repo")
    call_log = install_seams(
        monkeypatch,
        host_profile=HOST_PROFILE_THIRD_PARTY,
        claude_outcome=claude_served(),
        working_directory=working_directory,
    )

    run_review(working_directory, session_model=FIXTURE_SESSION_OPUS)

    assert call_log.is_stdin_empty is True
    assert call_log.claude_working_directory == working_directory


def test_wait_reports_reset_without_running_git_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reset_at = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    call_log = install_seams(
        monkeypatch,
        host_profile=HOST_PROFILE_THIRD_PARTY,
        claude_outcome=JobOutcome(WAIT_EXIT_CODE, "", "", None, (), "wait", None, reset_at),
    )
    monkeypatch.setattr(
        invoker,
        "review_git_status_runner",
        lambda *args, **kwargs: pytest.fail("wait must not inspect the tree"),
    )

    outcome = run_review(tmp_path, session_model=FIXTURE_SESSION_SONNET)

    assert call_log.claude_calls == 1
    assert outcome.served_command is None
    assert outcome.status == "wait"
    assert outcome.wait_reset_at == reset_at.isoformat()
    assert outcome.returncode == WAIT_EXIT_CODE
