import json
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
    run_digest,
    installed_files,
    prepare_workspace,
    remove_workspace,
    run_session,
    run_until_timeout,
    session_words,
    unscorable,
    write_trace,
)

STREAM_AND_TRUNCATED_REPORT = (
    "import sys\n"
    "from pathlib import Path\n"
    "print('invalid')\n"
    "print('[]')\n"
    "print('{\"type\": \"result\"}')\n"
    "Path(sys.argv[1]).write_text('{\"final_decision\": ', encoding='utf-8')\n"
)
IGNORE_STDIN_AND_SLEEP = "import time; time.sleep(60)"
LEAVE_A_BEATING_GRANDCHILD_AND_EXIT = (
    "import subprocess, sys\n"
    "beat = 'import sys, time\\nfrom pathlib import Path\\nwhile True:\\n    Path(sys.argv[1]).write_text(str(time.monotonic()), encoding=\\'utf-8\\')\\n    time.sleep(0.05)\\n'\n"
    "subprocess.Popen([sys.executable, '-c', beat, sys.argv[1]])\n"
)
START_A_BEATING_GRANDCHILD = (
    "import subprocess, sys, time\n"
    "beat = 'import sys, time\\nfrom pathlib import Path\\nwhile True:\\n    Path(sys.argv[1]).write_text(str(time.monotonic()), encoding=\\'utf-8\\')\\n    time.sleep(0.05)\\n'\n"
    "subprocess.Popen([sys.executable, '-c', beat, sys.argv[1]])\n"
    "time.sleep(60)\n"
)
ECHO_THE_PROMPT_AS_A_RESULT = (
    "import json, sys\n"
    "print(json.dumps({'type': 'result', 'result': sys.stdin.read()}))\n"
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
    all_words = session_words(SessionSettings("model", "low", 2, 10))
    brokered = brokered_words(Path("report.json"), all_words)

    assert all_words[:4] == ["claude", "-p", "--model", "model"]
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
    assert files_digest({"a": b"x\0b\0"}) != files_digest({"a": b"x", "b": b""})
    assert files_digest({".claude/rules/index.md": b"Index."}) == "34db5a63f317"


def test_installed_files_reads_each_source_under_its_workspace_path() -> None:
    all_installs = [("packages/claude-dev-env/rules/index.md", ".claude/rules/index.md")]
    repository_root = Path(__file__).resolve().parents[3]

    assert installed_files(all_installs) == {
        ".claude/rules/index.md": (repository_root / "packages/claude-dev-env/rules/index.md").read_bytes()
    }
    assert installed_files([]) == {}


def test_prepare_workspace_installs_the_bytes_it_is_given() -> None:
    workspace = prepare_workspace({".claude/rules/index.md": b"Read once.\n"})
    try:
        assert (workspace / ".claude/rules/index.md").read_bytes() == b"Read once.\n"
    finally:
        remove_workspace(workspace)


def test_run_session_sends_the_prompt_on_standard_input(tmp_path: Path) -> None:
    all_claude_words: list[list[str]] = []

    def echo_the_prompt(report_path: Path, claude_words: list[str]) -> list[str]:
        all_claude_words.append(claude_words)
        return [sys.executable, "-c", ECHO_THE_PROMPT_AS_A_RESULT]

    session = run_session(tmp_path, 'Fix the typo "recieve" & commit', SessionSettings("model", "low", 1, 60), echo_the_prompt)

    assert session.all_events == [{"type": "result", "result": 'Fix the typo "recieve" & commit'}]
    assert not any("recieve" in each_word for each_word in all_claude_words[0])


def test_write_trace_writes_the_turns_under_the_case_and_rep(tmp_path: Path) -> None:
    (tmp_path / "traces").mkdir()
    session = SessionRun([{"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}], 0.0, 0, {})

    write_trace({"id": "f01", "prompt": "the ask"}, 2, tmp_path, session)

    assert json.loads((tmp_path / "traces/f01_rep2.json").read_text(encoding="utf-8")) == [
        {"role": "user", "content": "the ask"},
        {"role": "assistant", "content": "done"},
    ]


def test_remove_workspace_deletes_a_committed_workspace_with_read_only_objects() -> None:
    workspace = prepare_workspace({})
    assert (workspace / ".git").is_dir()

    remove_workspace(workspace)

    assert not workspace.exists()


def test_run_until_timeout_stops_the_grandchild_a_launcher_started(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout(
            [sys.executable, "-c", START_A_BEATING_GRANDCHILD, str(heartbeat_path)], tmp_path, capture_file, 3, b""
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


def test_run_until_timeout_times_out_while_a_child_ignores_large_input(tmp_path: Path) -> None:
    started = time.monotonic()
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout([sys.executable, "-c", IGNORE_STDIN_AND_SLEEP], tmp_path, capture_file, 2, b"x" * 10_000_000)

    assert exit_code is None
    assert time.monotonic() - started < 20


def test_run_until_timeout_stops_a_background_process_left_by_a_clean_exit(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout(
            [sys.executable, "-c", LEAVE_A_BEATING_GRANDCHILD_AND_EXIT, str(heartbeat_path)], tmp_path, capture_file, 30, b""
        )
    time.sleep(0.5)
    beat_after_exit = heartbeat_path.read_text(encoding="utf-8") if heartbeat_path.exists() else ""
    time.sleep(0.5)

    assert exit_code == 0
    assert (heartbeat_path.read_text(encoding="utf-8") if heartbeat_path.exists() else "") == beat_after_exit


def test_run_digest_changes_with_files_settings_or_grader_source(tmp_path: Path) -> None:
    grader_path = tmp_path / "grading.py"
    grader_path.write_text("PASS = 1\n", encoding="utf-8")
    files = {".claude/rules/index.md": b"Index."}
    settings = {"model": "claude-opus-5-5", "max_turns": 6}
    digest = run_digest(files, settings, [grader_path])

    assert digest == run_digest(dict(files), dict(settings), [grader_path])
    assert digest != run_digest({".claude/rules/index.md": b"Index!"}, settings, [grader_path])
    assert digest != run_digest(files, {**settings, "max_turns": 3}, [grader_path])
    grader_path.write_text("PASS = 2\n", encoding="utf-8")
    assert digest != run_digest(files, settings, [grader_path])
