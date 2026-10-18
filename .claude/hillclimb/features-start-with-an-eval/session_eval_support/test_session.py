"""Behavior tests for session event reading and capture cleanup."""

import string
import subprocess
import tempfile
from pathlib import Path

import pytest

from session_eval_support import session
from session_eval_support.session import (
    SessionSettings,
    final_event,
    installed_files_digest,
    prepare_workspace,
    remove_directory,
    served_models,
    trace_turns,
)

INSTALLED_RULE = "packages/claude-dev-env/rules/index.md"


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


def test_installed_files_digest_is_empty_without_installs_and_short_hex_with_them() -> (
    None
):
    assert installed_files_digest([]) == ""
    digest = installed_files_digest([(INSTALLED_RULE, ".claude/rules/index.md")])
    assert len(digest) == 12
    assert set(digest) <= set(string.hexdigits.lower())


def test_prepare_workspace_commits_the_fixture_and_the_installed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    workspace = prepare_workspace([(INSTALLED_RULE, ".claude/rules/index.md")])

    assert (workspace / "jobs" / "cli.py").is_file()
    assert (workspace / ".claude" / "rules" / "index.md").is_file()
    committed = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    assert committed.stdout == "fixture\n"


def test_trace_turns_lists_the_prompt_then_each_block_in_stream_order() -> None:
    all_events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Starting."},
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "a"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "done"}]},
        },
    ]

    assert [each_turn["role"] for each_turn in trace_turns("ask", all_events)] == [
        "user",
        "assistant",
        "tool_call",
        "tool_result",
    ]


def test_remove_directory_deletes_the_tree(tmp_path: Path) -> None:
    directory = tmp_path / "workspace"
    (directory / ".git").mkdir(parents=True)

    remove_directory(directory)

    assert not directory.exists()


def test_remove_directory_logs_a_directory_it_could_not_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    directory = tmp_path / "workspace"
    directory.mkdir()
    monkeypatch.setattr(session, "force_rmtree", lambda target_path: None)

    remove_directory(directory)

    assert f"could not delete {directory}" in caplog.text


def test_prepare_workspace_deletes_the_directory_when_setup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        session, "ALL_GIT_INIT_COMMANDS", (("git", "not-a-git-command"),)
    )

    with pytest.raises(subprocess.CalledProcessError):
        prepare_workspace([])

    assert list(tmp_path.iterdir()) == []
