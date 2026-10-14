import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support import session
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    brokered_words,
    files_digest,
    harness_sources,
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
CLOSE_STDIN_AND_WAIT = "import os, time; os.close(0); time.sleep(1)"
PRINT_A_SEPARATED_RESULT_AND_A_CUT_REPORT = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.stdout.buffer.write('{\"type\": \"result\", \"result\": \"one\\u2028two\"}\\n'.encode('utf-8'))\n"
    "Path(sys.argv[1]).write_bytes(b'{\"final_decision\": \"caf\\xc3')\n"
)
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


def test_run_digest_changes_with_files_settings_or_harness_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session, "REPOSITORY_ROOT", tmp_path)
    rules_grader = tmp_path / "rules" / "grading.py"
    shared_grader = tmp_path / "shared" / "grading.py"
    for each_path in (rules_grader, shared_grader):
        each_path.parent.mkdir()
        each_path.write_text("PASS = 1\n", encoding="utf-8")
    files = {".claude/rules/index.md": b"Index."}
    settings = {"model": "claude-opus-5-5", "max_turns": 6}
    digest = run_digest(files, settings, [rules_grader, shared_grader])

    assert digest == run_digest(dict(files), dict(settings), [rules_grader, shared_grader])
    assert digest != run_digest(files, settings, [shared_grader])
    assert digest != run_digest({".claude/rules/index.md": b"Index!"}, settings, [rules_grader, shared_grader])
    assert digest != run_digest(files, {**settings, "max_turns": 3}, [rules_grader, shared_grader])
    rules_grader.write_text("PASS = 2\n", encoding="utf-8")
    assert digest != run_digest(files, settings, [rules_grader, shared_grader])


def test_harness_sources_keeps_source_files_and_leaves_out_tests_and_caches(tmp_path: Path) -> None:
    package = tmp_path / "support"
    (package / "config").mkdir(parents=True)
    (package / "__pycache__").mkdir()
    for each_name in ("grading.py", "config/constants.py", "test_grading.py", "__pycache__/grading.py", "notes.md"):
        (package / each_name).write_text("x = 1\n", encoding="utf-8")
    runner = tmp_path / "run.py"
    runner.write_text("x = 1\n", encoding="utf-8")

    assert harness_sources(package, runner) == sorted(
        [(package / "grading.py").resolve(), (package / "config/constants.py").resolve(), runner.resolve()]
    )


def test_prepare_workspace_removes_the_directory_when_filling_it_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    all_created: list[Path] = []
    make_directory = tempfile.mkdtemp

    def record(**all_options: str) -> str:
        created = make_directory(**all_options)
        all_created.append(Path(created))
        return created

    monkeypatch.setattr(session.tempfile, "mkdtemp", record)
    monkeypatch.setattr(session, "ALL_GIT_INIT_COMMANDS", (("git", "no-such-subcommand"),))

    with pytest.raises(subprocess.CalledProcessError):
        prepare_workspace({})
    assert not all_created[0].exists()


def test_run_until_timeout_logs_a_failed_input_write_and_still_returns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout(
            [sys.executable, "-c", CLOSE_STDIN_AND_WAIT], tmp_path, capture_file, 30, b"x" * 10_000_000
        )

    assert exit_code == 0
    assert "standard input to pid" in caplog.text


def test_run_session_keeps_an_event_with_a_line_separator_and_survives_a_cut_report(tmp_path: Path) -> None:
    def print_and_cut(report_path: Path, claude_words: list[str]) -> list[str]:
        return [sys.executable, "-c", PRINT_A_SEPARATED_RESULT_AND_A_CUT_REPORT, str(report_path)]

    session_run = run_session(tmp_path, "ask", SessionSettings("model", "low", 1, 60), print_and_cut)

    assert session_run.all_events == [{"type": "result", "result": "one\u2028two"}]
    assert session_run.broker_report == {}


def test_run_digest_keys_a_harness_file_outside_the_repository_by_its_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session, "REPOSITORY_ROOT", tmp_path / "repository")
    outside_grader = tmp_path / "elsewhere" / "grading.py"
    outside_grader.parent.mkdir()
    outside_grader.write_text("PASS = 1\n", encoding="utf-8")

    assert len(run_digest({}, {}, [outside_grader])) == 12


class _FakeKernel:
    def __init__(self, job_handle: int | None, resume_status: int = 0, process_handle: int | None = 77) -> None:
        self.reply_by_name: dict[str, int | None] = {
            "CreateJobObjectW": job_handle,
            "NtResumeProcess": resume_status,
            "OpenProcess": process_handle,
        }
        self.all_calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        def record(*all_arguments: object) -> int | None:
            self.all_calls.append(name)
            return self.reply_by_name.get(name, 77)
        return record


def _run_as_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kernel: _FakeKernel, script: str = "pass") -> int | None:
    monkeypatch.setattr(session, "_windows_kernel", lambda: kernel)
    monkeypatch.setattr(session, "_windows_native", lambda: kernel)
    monkeypatch.setattr(session, "_popen_options", lambda: {})
    monkeypatch.setattr(session.sys, "platform", "win32")
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        return run_until_timeout([sys.executable, "-c", script], tmp_path, capture_file, 30, b"")


def test_windows_runs_start_suspended_join_a_job_and_end_it_after_a_clean_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    kernel = _FakeKernel(job_handle=55)

    assert _run_as_windows(monkeypatch, tmp_path, kernel) == 0
    assert kernel.all_calls == [
        "OpenProcess", "CreateJobObjectW", "AssignProcessToJobObject", "NtResumeProcess", "CloseHandle",
        "TerminateJobObject", "CloseHandle",
    ]


def test_windows_runs_terminate_the_command_when_the_job_cannot_be_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kernel = _FakeKernel(job_handle=None)

    assert _run_as_windows(monkeypatch, tmp_path, kernel) == 0
    assert kernel.all_calls == ["OpenProcess", "CreateJobObjectW", "TerminateProcess", "CloseHandle"]
    assert "no job object for pid" in caplog.text


def test_windows_runs_terminate_a_command_that_fails_to_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kernel = _FakeKernel(job_handle=55, resume_status=0xC0000008)

    assert _run_as_windows(monkeypatch, tmp_path, kernel) == 0
    assert kernel.all_calls[:5] == ["OpenProcess", "CreateJobObjectW", "AssignProcessToJobObject", "NtResumeProcess", "TerminateProcess"]
    assert "resuming pid" in caplog.text and "0xc0000008" in caplog.text


def test_popen_options_start_suspended_on_windows_and_in_a_new_session_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session.sys, "platform", "win32")
    assert session._popen_options() == {"creationflags": 4}
    monkeypatch.setattr(session.sys, "platform", "linux")
    assert session._popen_options() == {"start_new_session": True}


def test_windows_runs_kill_a_command_whose_handle_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kernel = _FakeKernel(job_handle=55, process_handle=None)

    assert _run_as_windows(monkeypatch, tmp_path, kernel, IGNORE_STDIN_AND_SLEEP) == -signal.SIGKILL
    assert kernel.all_calls == ["OpenProcess"]
    assert "no handle for pid" in caplog.text


def test_windows_runs_kill_the_command_when_joining_a_job_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    all_processes: list[subprocess.Popen[bytes]] = []
    start_process = subprocess.Popen

    def record(*all_arguments: object, **all_options: object) -> subprocess.Popen[bytes]:
        process = start_process(*all_arguments, **all_options)
        all_processes.append(process)
        return process

    def missing_native() -> object:
        raise AttributeError("NtResumeProcess")

    monkeypatch.setattr(session.subprocess, "Popen", record)
    monkeypatch.setattr(session, "_windows_kernel", lambda: _FakeKernel(job_handle=55))
    monkeypatch.setattr(session, "_windows_native", missing_native)
    monkeypatch.setattr(session, "_popen_options", lambda: {})
    monkeypatch.setattr(session.sys, "platform", "win32")

    with pytest.raises(AttributeError), (tmp_path / "capture.txt").open("wb") as capture_file:
        run_until_timeout([sys.executable, "-c", IGNORE_STDIN_AND_SLEEP], tmp_path, capture_file, 30, b"")
    assert all_processes[0].returncode == -signal.SIGKILL


def test_run_until_timeout_stops_the_group_before_the_leader_is_reaped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    all_leader_states: list[object] = []
    kill_group = os.killpg

    def check_leader_then_kill(process_group: int, signal_number: int) -> None:
        all_leader_states.append(os.waitid(os.P_PID, process_group, os.WEXITED | os.WNOHANG | os.WNOWAIT))
        kill_group(process_group, signal_number)

    monkeypatch.setattr(session.os, "killpg", check_leader_then_kill)
    with (tmp_path / "capture.txt").open("wb") as capture_file:
        exit_code = run_until_timeout([sys.executable, "-c", "raise SystemExit(4)"], tmp_path, capture_file, 30, b"")

    assert exit_code == 4
    assert all_leader_states[0] is not None


def test_trace_turns_skip_events_whose_types_are_not_strings() -> None:
    all_events = [{"type": ["assistant"], "message": {"content": [{"type": {"text": 1}, "text": "x"}]}}]

    assert session.trace_turns("ask", all_events) == [{"role": "user", "content": "ask"}]


def test_run_digest_keys_a_symlinked_harness_folder_by_its_repository_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "grading.py").write_text("PASS = 1\n", encoding="utf-8")
    repository.mkdir()
    (repository / "flow").symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(session, "REPOSITORY_ROOT", repository)

    assert session._repository_key(repository / "flow" / "grading.py") == "flow/grading.py"
    assert harness_sources(repository / "flow") == [repository / "flow" / "grading.py"]


def test_run_session_warns_about_an_unreadable_stream_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    def print_a_broken_line(report_path: Path, claude_words: list[str]) -> list[str]:
        return [sys.executable, "-c", "print('not json'); print('{\"type\": \"result\"}')"]

    session_run = run_session(tmp_path, "ask", SessionSettings("model", "low", 1, 60), print_a_broken_line)

    assert session_run.all_events == [{"type": "result"}]
    assert "skipped unreadable line 1" in caplog.text


def test_remove_workspace_warns_when_the_directory_stays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(session, "force_rmtree", lambda target_path: None)

    remove_workspace(tmp_path)

    assert f"workspace {tmp_path} could not be removed" in caplog.text
