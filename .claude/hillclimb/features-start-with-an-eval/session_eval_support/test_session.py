"""Behavior tests for session event reading and capture cleanup."""

import tempfile
from pathlib import Path

import pytest

from session_eval_support import session
from session_eval_support.session import (
    SessionSettings,
    final_event,
    served_models,
)


def test_final_event_returns_last_result() -> None:
    events = [
        {"type": "result", "subtype": "first"},
        {"type": "assistant"},
        {"type": "result", "subtype": "last"},
    ]

    assert final_event(events) == events[-1]
    assert final_event([{"type": "assistant"}]) is None


def test_served_models_sorts_usage_keys() -> None:
    assert served_models({"modelUsage": {"z": {}, "a": {}}}) == ["a", "z"]
    assert served_models({}) == []


def test_run_session_reads_the_stream_then_deletes_its_capture_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def _write_stream(
        all_command_words: list[str],
        session_directory: Path,
        stream_path: Path,
        timeout_seconds: int,
    ) -> int:
        stream_path.write_text('{"type": "result", "subtype": "success"}\n')
        return 0

    monkeypatch.setattr(session, "_run_command", _write_stream)

    session_run = session.run_session(
        workspace, "ask", SessionSettings("claude-haiku", "low", 1, 1)
    )

    assert session_run.all_events == [{"type": "result", "subtype": "success"}]
    assert [each_path.name for each_path in tmp_path.iterdir()] == ["workspace"]
