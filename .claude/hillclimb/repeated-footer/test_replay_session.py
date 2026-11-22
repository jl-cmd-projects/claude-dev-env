import os
import sys
from pathlib import Path

import pytest
from repeated_footer_eval_support.config.constants import HOOKS_DIRECTORY
from repeated_footer_eval_support.replay_session import (
    ReplayGateRunFatal,
    ReplaySession,
    gate_environment,
    require_stub_judge_first,
    write_stub_judge,
    write_task_store,
)

ALL_TASKS = [{"id": "1", "subject": "Ship pull request 8590", "status": "in_progress"}]


def test_should_write_each_task_to_the_session_store(tmp_path: Path) -> None:
    claude_home = tmp_path / "home" / ".claude"
    write_task_store(claude_home, ALL_TASKS)
    assert (claude_home / "tasks" / "repeated-footer-eval" / "1.json").is_file()


def test_should_write_the_stand_in_judge_for_posix_and_windows(tmp_path: Path) -> None:
    stub_directory = write_stub_judge(tmp_path)
    assert (stub_directory / "claude").is_file()
    windows_launcher = (stub_directory / "claude.cmd").read_text(encoding="utf-8")
    assert sys.executable in windows_launcher
    assert "%~dp0claude" in windows_launcher


def test_should_put_the_stand_in_judge_first_on_the_gate_path(tmp_path: Path) -> None:
    claude_home = tmp_path / "home" / ".claude"
    stub_directory = write_stub_judge(tmp_path)
    all_variables = gate_environment(tmp_path, claude_home, stub_directory)
    assert all_variables["PATH"].split(os.pathsep)[0] == str(stub_directory)
    assert all_variables["CLAUDE_CONFIG_DIR"] == str(claude_home)
    require_stub_judge_first(stub_directory, all_variables["PATH"])


def test_should_stop_the_replay_when_another_claude_answers_first(
    tmp_path: Path,
) -> None:
    (tmp_path / "stub").mkdir()
    stub_directory = write_stub_judge(tmp_path / "stub")
    (tmp_path / "other").mkdir()
    other_directory = write_stub_judge(tmp_path / "other")
    with pytest.raises(ReplayGateRunFatal):
        require_stub_judge_first(
            stub_directory, os.pathsep.join([str(other_directory), str(stub_directory)])
        )


def test_should_stop_the_replay_when_a_gate_cannot_start(tmp_path: Path) -> None:
    session = ReplaySession(tmp_path, ALL_TASKS)
    session.add_user_text("Ship it.", "human")
    with pytest.raises(ReplayGateRunFatal, match="exited with code"):
        session.stop_reasons(tmp_path / "missing-hooks", "Done.", False)


def test_should_run_the_gates_from_a_relative_hooks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = ReplaySession(tmp_path / "session", ALL_TASKS)
    session.add_user_text("Ship it.", "human")
    session.add_tool_calls(["Bash"])
    session.add_reply("Done.")
    monkeypatch.chdir(HOOKS_DIRECTORY.parent)
    all_reasons = session.stop_reasons(Path(HOOKS_DIRECTORY.name), "Done.", False)
    assert any("In progress footer" in each_reason for each_reason in all_reasons)
