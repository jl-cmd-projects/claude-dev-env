import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    brokered_words,
    run_session,
    session_words,
    unscorable,
)

STREAM_AND_TRUNCATED_REPORT = (
    "import sys\n"
    "from pathlib import Path\n"
    "print('invalid')\n"
    "print('[]')\n"
    "print('{\"type\": \"result\"}')\n"
    "Path(sys.argv[1]).write_text('{\"final_decision\": ', encoding='utf-8')\n"
)


def test_unscorable_reports_a_broker_wait_before_examining_events() -> None:
    session = SessionRun([], 0.0, 3, {"final_decision": "wait"})
    settings = SessionSettings("model", "low", 1, 10)

    assert unscorable(session, settings) == ("broker-wait", "wait")


def test_unscorable_reports_a_timeout_and_a_served_model_mismatch() -> None:
    settings = SessionSettings("claude-opus", "low", 1, 10)
    finished = [{"type": "result", "subtype": "success", "modelUsage": {"claude-haiku": {}}}]

    assert unscorable(SessionRun([], 0.0, None, {}), settings) == ("timeout", 10)
    assert unscorable(SessionRun(finished, 0.0, 0, {}), settings) == ("served-model-mismatch", ["claude-haiku"])


def test_brokered_words_wrap_the_session_command_after_the_report_path() -> None:
    all_words = session_words("hi", SessionSettings("model", "low", 2, 10))
    brokered = brokered_words(Path("report.json"), all_words)

    assert all_words[:3] == ["claude", "-p", "hi"]
    assert brokered[brokered.index("--report") + 1] == "report.json"
    assert brokered[-len(all_words) - 1 :] == ["--", *all_words]


def test_run_session_reads_the_stream_survives_a_truncated_report_and_removes_its_capture(tmp_path: Path) -> None:
    all_report_paths: list[Path] = []

    def write_stream_and_report(report_path: Path, all_claude_words: list[str]) -> list[str]:
        all_report_paths.append(report_path)
        return [sys.executable, "-c", STREAM_AND_TRUNCATED_REPORT, str(report_path)]

    session = run_session(tmp_path, "case prompt", SessionSettings("model", "low", 1, 60), write_stream_and_report)

    assert session.all_events == [{"type": "result"}]
    assert session.exit_code == 0
    assert session.broker_report == {}
    assert not all_report_paths[0].parent.exists()
