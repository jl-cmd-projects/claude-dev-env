"""Shared fixtures for broker keyword forwarding tests."""

from __future__ import annotations

import pytest

from dev_env_scripts_constants.account_broker_constants import JobOutcome, Product

FIXTURE_ENCODING_KEYWORD_NAME = "encoding"
FIXTURE_ERRORS_KEYWORD_NAME = "errors"
FIXTURE_CHAIN_ENCODING = "utf-8"
FIXTURE_CHAIN_ERRORS = "replace"


def install_codec_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chain_stdout: str,
    runner_host: object,
    runner_attribute_name: str,
) -> dict[str, object]:
    observed_options: dict[str, object] = {}

    def recording_runner(product: Product, argv: list[str], **options: object) -> JobOutcome:
        assert product is Product.CLAUDE
        assert argv[0] == "claude"
        observed_options.update(options)
        return JobOutcome(0, chain_stdout, "", "main", (("main", "served"),), "served", None, None)

    monkeypatch.setattr(runner_host, runner_attribute_name, recording_runner)
    return observed_options
