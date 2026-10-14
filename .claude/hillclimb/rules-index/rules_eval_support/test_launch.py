import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support import launch
from rules_eval_support.launch import launch_words, run_session
from session_eval_support.session import SessionSettings

STREAM_AND_TRUNCATED_REPORT = (
    "import sys\n"
    "from pathlib import Path\n"
    "print('invalid')\n"
    "print('[]')\n"
    "print('{\"type\": \"result\"}')\n"
    "Path(sys.argv[1]).write_text('{\"final_decision\": ', encoding='utf-8')\n"
)


def test_launch_words_resolves_the_executable_directly_and_wraps_it_for_the_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    command = ["claude", "-p", "case prompt"]
    monkeypatch.setattr(launch.shutil, "which", lambda name: "/opt/bin/" + name)

    assert launch_words(Path("report.json"), command, is_direct=True) == ["/opt/bin/claude", "-p", "case prompt"]
    brokered = launch_words(Path("report.json"), command, is_direct=False)
    assert brokered[-4:] == ["--", *command]
    assert brokered[brokered.index("--report") + 1] == "report.json"


def test_run_session_reads_the_stream_survives_a_truncated_report_and_removes_its_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    all_report_paths: list[Path] = []

    def write_stream_and_report(report_path: Path, all_claude_words: list[str], is_direct: bool) -> list[str]:
        all_report_paths.append(report_path)
        return [sys.executable, "-c", STREAM_AND_TRUNCATED_REPORT, str(report_path)]

    monkeypatch.setattr(launch, "launch_words", write_stream_and_report)

    session = run_session(tmp_path, "case prompt", SessionSettings("model", "low", 1, 60), is_direct=True)

    assert session.all_events == [{"type": "result"}]
    assert session.exit_code == 0
    assert session.broker_report == {}
    assert not all_report_paths[0].parent.exists()
