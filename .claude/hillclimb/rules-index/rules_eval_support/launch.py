"""Start a headless Claude Code session, through the account broker or on the caller's account."""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rules_eval_support.config.constants import BROKER_SCRIPT
from session_eval_support.config.constants import SESSION_SETTING_SOURCES
from session_eval_support.session import SessionRun, SessionSettings


def launch_words(report_path: Path, all_claude_words: list[str], is_direct: bool) -> list[str]:
    """Return the command that starts one headless Claude call.

    ::

        launch_words(r, ["claude", "-p", "hi"], is_direct=True)
        -> ["claude", "-p", "hi"]
        launch_words(r, ["claude", "-p", "hi"], is_direct=False)
        -> [python, account_broker.py, "run", "--product", "claude", "--report", r, "--", "claude", "-p", "hi"]

    Args:
        report_path: Where the broker writes its report.
        all_claude_words: The claude command and its arguments.
        is_direct: Whether to run on the account the caller's session uses.

    Returns:
        The full argument list for subprocess.
    """
    if is_direct:
        return [shutil.which(all_claude_words[0]) or all_claude_words[0], *all_claude_words[1:]]
    return [sys.executable, str(BROKER_SCRIPT), "run", "--product", "claude", "--report", str(report_path), "--", *all_claude_words]


def _read_events(stream_path: Path) -> list[dict[str, object]]:
    all_events: list[dict[str, object]] = []
    for each_line in stream_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            each_event = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if isinstance(each_event, dict):
            all_events.append(each_event)
    return all_events


def run_session(workspace: Path, prompt: str, settings: SessionSettings, is_direct: bool) -> SessionRun:
    """Run the prompt as one headless session in the workspace and read its stream.

    Args:
        workspace: The prepared workspace, used as the session's directory.
        prompt: The case's ask.
        settings: The model, effort, turn cap and wall-clock ceiling.
        is_direct: Whether to skip the broker and run on the caller's account.

    Returns:
        The stream, latency, exit code (None on timeout) and broker report.
    """
    capture_directory = Path(tempfile.mkdtemp(prefix=workspace.name + "-out-"))
    stream_path = capture_directory / "stream.jsonl"
    report_path = capture_directory / "broker-report.json"
    all_claude_words = [
        "claude", "-p", prompt, "--model", settings.model, "--effort", settings.effort,
        "--max-turns", str(settings.max_turns), "--output-format", "stream-json", "--verbose",
        "--setting-sources", SESSION_SETTING_SOURCES,
    ]
    started = time.monotonic()
    with stream_path.open("w", encoding="utf-8") as stream_file:
        try:
            exit_code: int | None = subprocess.run(
                launch_words(report_path, all_claude_words, is_direct),
                cwd=workspace, stdout=stream_file, stderr=subprocess.DEVNULL,
                timeout=settings.timeout_seconds, check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            exit_code = None
    latency_seconds = time.monotonic() - started
    broker_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return SessionRun(_read_events(stream_path), latency_seconds, exit_code, broker_report)
