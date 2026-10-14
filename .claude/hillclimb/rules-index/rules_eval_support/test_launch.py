import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support import launch
from rules_eval_support.launch import launch_words, run_session
from session_eval_support.session import SessionSettings

RESULT_EVENT_SCRIPT = "print('{\"type\": \"result\"}')"


def test_launch_words_resolves_the_executable_directly_and_wraps_it_for_the_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    command = ["claude", "-p", "case prompt"]
    monkeypatch.setattr(launch.shutil, "which", lambda name: "/opt/bin/" + name)

    assert launch_words(Path("report.json"), command, is_direct=True) == ["/opt/bin/claude", "-p", "case prompt"]
    brokered = launch_words(Path("report.json"), command, is_direct=False)
    assert brokered[-4:] == ["--", *command]
    assert brokered[brokered.index("--report") + 1] == "report.json"


def test_run_session_launches_through_launch_words_with_the_direct_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    all_direct_flags: list[bool] = []

    def print_a_result(report_path: Path, all_claude_words: list[str], is_direct: bool) -> list[str]:
        all_direct_flags.append(is_direct)
        return [sys.executable, "-c", RESULT_EVENT_SCRIPT]

    monkeypatch.setattr(launch, "launch_words", print_a_result)

    session = run_session(tmp_path, "case prompt", SessionSettings("model", "low", 1, 60), is_direct=True)

    assert session.all_events == [{"type": "result"}]
    assert all_direct_flags == [True]
