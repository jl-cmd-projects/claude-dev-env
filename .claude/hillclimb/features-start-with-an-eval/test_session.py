import sys
import time
from pathlib import Path


flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    brokered_words,
    files_digest,
    installed_files_digest,
    prepare_workspace,
    remove_workspace,
    run_session,
    run_until_timeout,
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
START_A_BEATING_GRANDCHILD = (
    "import subprocess, sys, time\n"
    "beat = 'import sys, time\\nfrom pathlib import Path\\nwhile True:\\n    Path(sys.argv[1]).write_text(str(time.monotonic()), encoding=\\'utf-8\\')\\n    time.sleep(0.05)\\n'\n"
    "subprocess.Popen([sys.executable, '-c', beat, sys.argv[1]])\n"
    "time.sleep(60)\n"
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


def test_files_digest_changes_with_a_path_or_bytes_and_keeps_fields_apart() -> None:
    digest = files_digest({"a/rule.md": b"Rule."})

    assert digest == files_digest({"a/rule.md": b"Rule."})
    assert len(digest) == 12
    assert digest != files_digest({"b/rule.md": b"Rule."})
    assert digest != files_digest({"a/rule.md": b"Rule!"})
    assert files_digest({"a": b"bc"}) != files_digest({"ab": b"c"})


def test_installed_files_digest_hashes_each_source_under_its_workspace_path() -> None:
    all_installs = [("packages/claude-dev-env/rules/index.md", ".claude/rules/index.md")]
    repository_root = Path(__file__).resolve().parents[3]

    assert installed_files_digest(all_installs) == files_digest(
        {".claude/rules/index.md": (repository_root / "packages/claude-dev-env/rules/index.md").read_bytes()}
    )
    assert installed_files_digest([]) == files_digest({})


def test_remove_workspace_deletes_a_committed_workspace_with_read_only_objects() -> None:
    workspace = prepare_workspace([])
    assert (workspace / ".git").is_dir()

    remove_workspace(workspace)

    assert not workspace.exists()


def test_run_until_timeout_stops_the_grandchild_a_launcher_started(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout(
            [sys.executable, "-c", START_A_BEATING_GRANDCHILD, str(heartbeat_path)], tmp_path, capture_file, 3, None
        )
    time.sleep(0.5)
    beat_after_timeout = heartbeat_path.read_text(encoding="utf-8")
    time.sleep(0.5)

    assert exit_code is None
    assert heartbeat_path.read_text(encoding="utf-8") == beat_after_timeout


def test_run_until_timeout_passes_standard_input_and_returns_the_exit_code(tmp_path: Path) -> None:
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper()); sys.exit(3)"],
            tmp_path,
            capture_file,
            30,
            b"judge me",
        )

    assert exit_code == 3
    assert (tmp_path / "capture.txt").read_text(encoding="utf-8") == "JUDGE ME"
