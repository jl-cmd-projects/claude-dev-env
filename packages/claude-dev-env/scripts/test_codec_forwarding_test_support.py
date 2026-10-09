from __future__ import annotations

from types import SimpleNamespace

import pytest

from codec_forwarding_test_support import install_codec_seams
from dev_env_scripts_constants.account_broker_constants import Product


def test_should_record_runner_options_and_return_served_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_host = SimpleNamespace(run=None)
    observed_options = install_codec_seams(
        monkeypatch,
        chain_stdout='{"result":"done"}',
        runner_host=runner_host,
        runner_attribute_name="run",
    )

    outcome = runner_host.run(
        Product.CLAUDE, ["claude", "-p"], encoding="utf-8", errors="replace"
    )

    assert observed_options == {"encoding": "utf-8", "errors": "replace"}
    assert outcome.stdout == '{"result":"done"}'
    assert outcome.status == "served"
