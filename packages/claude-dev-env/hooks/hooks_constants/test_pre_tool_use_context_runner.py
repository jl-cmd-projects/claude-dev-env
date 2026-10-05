import io
import json
import sys

import pytest

from hooks_constants.pre_tool_use_context_runner import run_context_hook


def _feed_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8"))))


def test_prints_the_decided_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _feed_stdin(monkeypatch, json.dumps({"tool_name": "Agent"}))
    exit_code = run_context_hook(lambda payload: {"seen": payload["tool_name"]})
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"seen": "Agent"}


def test_prints_nothing_when_the_decision_is_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _feed_stdin(monkeypatch, json.dumps({"tool_name": "Bash"}))
    assert run_context_hook(lambda payload: None) == 0
    assert capsys.readouterr().out == ""


def test_prints_nothing_for_empty_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _feed_stdin(monkeypatch, "")
    assert run_context_hook(lambda payload: {"never": True}) == 0
    assert capsys.readouterr().out == ""


def test_prints_nothing_and_exits_zero_when_the_decision_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise(payload: dict[str, object]) -> dict[str, object] | None:
        raise KeyError(payload["missing"])

    _feed_stdin(monkeypatch, json.dumps({"tool_name": "Agent"}))
    assert run_context_hook(_raise) == 0
    assert capsys.readouterr().out == ""
