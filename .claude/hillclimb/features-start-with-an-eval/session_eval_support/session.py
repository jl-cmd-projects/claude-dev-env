"""Run one case as a fresh headless Claude Code session through the account broker."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from session_eval_support.config.constants import (
    ALL_GIT_INIT_COMMANDS,
    ASSISTANT_EVENT_TYPE,
    BROKER_REPORT_FILE_NAME,
    BROKER_SCRIPT,
    FIXTURE_DIRECTORY,
    JSON_INDENT,
    REPOSITORY_ROOT,
    RESULT_EVENT_TYPE,
    STREAM_FILE_NAME,
    TEXT_BLOCK_TYPE,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_RESULT_PREVIEW_LENGTH,
    TOOL_USE_BLOCK_TYPE,
    USER_EVENT_TYPE,
    WORKSPACE_PREFIX,
)


@dataclass(frozen=True)
class SessionSettings:
    """The model settings every session in one run uses."""

    model: str
    effort: str
    max_turns: int
    timeout_seconds: int


@dataclass(frozen=True)
class SessionRun:
    """What one headless session left behind."""

    all_events: list[dict[str, object]]
    latency_seconds: float
    exit_code: int | None
    broker_report: dict[str, object]


def installed_files_digest(all_installs: list[tuple[str, str]]) -> str:
    """Return a short sha256 over the files a variant installs, or an empty string.

    Args:
        all_installs: Pairs of a repository path and its workspace path.
    """
    if not all_installs:
        return ""
    digest = hashlib.sha256()
    for each_source, _each_target in all_installs:
        digest.update((REPOSITORY_ROOT / each_source).read_bytes())
    return digest.hexdigest()[:12]


def prepare_workspace(all_installs: list[tuple[str, str]]) -> Path:
    """Copy the fixture project and the variant's files into a new git workspace.

    Args:
        all_installs: Pairs of a repository path and the workspace path it goes to.

    Returns:
        The workspace directory, committed on branch main.
    """
    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    shutil.copytree(FIXTURE_DIRECTORY, workspace, dirs_exist_ok=True)
    for each_source, each_target in all_installs:
        target_path = workspace / each_target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / each_source, target_path)
    for each_command in ALL_GIT_INIT_COMMANDS:
        subprocess.run(each_command, cwd=workspace, check=True, capture_output=True)
    return workspace


def _read_events(stream_path: Path) -> list[dict[str, object]]:
    all_events: list[dict[str, object]] = []
    if not stream_path.is_file():
        return all_events
    for each_line in stream_path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        try:
            each_event = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if isinstance(each_event, dict):
            all_events.append(each_event)
    return all_events


def run_session(workspace: Path, prompt: str, settings: SessionSettings) -> SessionRun:
    """Run the prompt as one headless session in the workspace and read its stream.

    The broker picks the account. The stream and the broker report land in a
    sibling directory, so the session under test never sees them.

    Args:
        workspace: The prepared workspace, used as the session's directory.
        prompt: The case's ask, sent as the first user turn.
        settings: The model, effort, turn cap and wall-clock ceiling.
    """
    output_directory = Path(tempfile.mkdtemp(prefix=workspace.name + "-out-"))
    stream_path = output_directory / STREAM_FILE_NAME
    report_path = output_directory / BROKER_REPORT_FILE_NAME
    command = [
        sys.executable,
        str(BROKER_SCRIPT),
        "run",
        "--product",
        "claude",
        "--report",
        str(report_path),
        "--",
        "claude",
        "-p",
        prompt,
        "--model",
        settings.model,
        "--effort",
        settings.effort,
        "--max-turns",
        str(settings.max_turns),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    started = time.monotonic()
    exit_code: int | None
    with stream_path.open("w", encoding="utf-8") as stream_file:
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                stdout=stream_file,
                stderr=subprocess.DEVNULL,
                timeout=settings.timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
    latency_seconds = time.monotonic() - started
    broker_report: dict[str, object] = {}
    if report_path.is_file():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            broker_report = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            broker_report = {}
    return SessionRun(
        _read_events(stream_path), latency_seconds, exit_code, broker_report
    )


def result_event(all_events: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the session's final result event, or None when it never finished.

    Args:
        all_events: The parsed stream.
    """
    return next(
        (
            each_event
            for each_event in reversed(all_events)
            if each_event.get("type") == RESULT_EVENT_TYPE
        ),
        None,
    )


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(each_part.get("text", ""))
            for each_part in content
            if isinstance(each_part, dict)
        )
    return ""


def trace_turns(
    prompt: str, all_events: list[dict[str, object]]
) -> list[dict[str, str]]:
    """Return the session as the report's trace turns.

    ::

        prompt, [assistant text, Skill tool_use, tool_result]
        -> user, assistant, tool_call, tool_result

    Args:
        prompt: The case's ask.
        all_events: The parsed stream.
    """
    all_turns: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    for each_event in all_events:
        message = each_event.get("message")
        if not isinstance(message, dict) or not isinstance(
            message.get("content"), list
        ):
            continue
        for each_block in message["content"]:
            if not isinstance(each_block, dict):
                continue
            block_type = each_block.get("type")
            if (
                each_event.get("type") == ASSISTANT_EVENT_TYPE
                and block_type == TEXT_BLOCK_TYPE
            ):
                all_turns.append(
                    {"role": "assistant", "content": str(each_block.get("text", ""))}
                )
            elif (
                each_event.get("type") == ASSISTANT_EVENT_TYPE
                and block_type == TOOL_USE_BLOCK_TYPE
            ):
                all_turns.append(
                    {
                        "role": "tool_call",
                        "name": str(each_block.get("name")),
                        "content": json.dumps(
                            each_block.get("input"), indent=JSON_INDENT
                        ),
                    }
                )
            elif (
                each_event.get("type") == USER_EVENT_TYPE
                and block_type == TOOL_RESULT_BLOCK_TYPE
            ):
                all_turns.append(
                    {
                        "role": "tool_result",
                        "content": _result_text(each_block.get("content"))[
                            :TOOL_RESULT_PREVIEW_LENGTH
                        ],
                    }
                )
    return all_turns


def served_models(result: Mapping[str, object]) -> list[str]:
    """Return the model ids the result event bills.

    Args:
        result: The session's result event.
    """
    model_usage = result.get("modelUsage")
    return sorted(model_usage) if isinstance(model_usage, dict) else []
