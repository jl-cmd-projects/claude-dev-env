"""Behavioral tests for text codec keyword forwarding in the ``/code-review`` invoker."""

from __future__ import annotations

from pathlib import Path

import invoke_code_review as invoker
import pytest
from codec_forwarding_test_support import (
    FIXTURE_CHAIN_ENCODING,
    FIXTURE_CHAIN_ERRORS,
    FIXTURE_ENCODING_KEYWORD_NAME,
    FIXTURE_ERRORS_KEYWORD_NAME,
    install_codec_seams,
)
from dev_env_scripts_constants.timing import DEFAULT_CODE_REVIEW_TIMEOUT_SECONDS

FIXTURE_CHAIN_STDOUT = '{"result":"review done"}'


def _install_invoker_codec_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    return install_codec_seams(
        monkeypatch,
        chain_stdout=FIXTURE_CHAIN_STDOUT,
        runner_host=invoker,
        runner_attribute_name="review_claude_runner",
    )


def test_forwards_text_codec_keywords_to_subprocess_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    all_observed_runner_keywords = _install_invoker_codec_seams(
        monkeypatch,
    )

    invoker._run_claude_with_empty_stdin(
        [],
        timeout_seconds=DEFAULT_CODE_REVIEW_TIMEOUT_SECONDS,
        working_directory=tmp_path,
    )

    assert (
        all_observed_runner_keywords[FIXTURE_ENCODING_KEYWORD_NAME]
        == FIXTURE_CHAIN_ENCODING
    )
    assert (
        all_observed_runner_keywords[FIXTURE_ERRORS_KEYWORD_NAME]
        == FIXTURE_CHAIN_ERRORS
    )


def test_empty_stdin_and_cwd_reach_broker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    all_observed_runner_keywords = _install_invoker_codec_seams(
        monkeypatch,
    )

    invoker._run_claude_with_empty_stdin(
        [],
        timeout_seconds=DEFAULT_CODE_REVIEW_TIMEOUT_SECONDS,
        working_directory=tmp_path,
    )

    assert all_observed_runner_keywords["stdin_text"] == ""
    assert all_observed_runner_keywords["cwd"] == tmp_path
