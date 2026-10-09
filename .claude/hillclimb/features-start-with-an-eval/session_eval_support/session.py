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
    NEWLINE,
    REPOSITORY_ROOT,
    RESULT_EVENT_TYPE,
    SESSION_SETTING_SOURCES,
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

    Returns:
        The first 12 hex digits of the digest, or an empty string for no installs.
    """
    if not all_installs:
        return ""
    digest = hashlib.sha256()
    for each_install in all_installs:
        digest.update((REPOSITORY_ROOT / each_install[0]).read_bytes())
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


def _session_command(
    report_path: Path, prompt: str, settings: SessionSettings
) -> list[str]:
    return [
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
        "--setting-sources",
        SESSION_SETTING_SOURCES,
    ]


def _read_broker_report(report_path: Path) -> dict[str, object]:
    if not report_path.is_file():
        return {}
    try:
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _run_command(
    all_command_words: list[str],
    workspace: Path,
    stream_path: Path,
    timeout_seconds: int,
) -> int | None:
    with stream_path.open("w", encoding="utf-8") as stream_file:
        try:
            completed = subprocess.run(
                all_command_words,
                cwd=workspace,
                stdout=stream_file,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None
    return completed.returncode


def run_session(workspace: Path, prompt: str, settings: SessionSettings) -> SessionRun:
    """Run the prompt as one headless session in the workspace and read its stream.

    The broker picks the account. The stream and the broker report land in a
    sibling directory, so the session under test never sees them.

    Args:
        workspace: The prepared workspace, used as the session's directory.
        prompt: The case's ask, sent as the first user turn.
        settings: The model, effort, turn cap and wall-clock ceiling.

    Returns:
        The stream, latency, exit code (None on timeout) and broker report.
    """
    capture_directory = Path(tempfile.mkdtemp(prefix=workspace.name + "-out-"))
    stream_path = capture_directory / STREAM_FILE_NAME
    report_path = capture_directory / BROKER_REPORT_FILE_NAME
    started = time.monotonic()
    exit_code = _run_command(
        _session_command(report_path, prompt, settings),
        workspace,
        stream_path,
        settings.timeout_seconds,
    )
    latency_seconds = time.monotonic() - started
    broker_report = _read_broker_report(report_path)
    return SessionRun(
        _read_events(stream_path), latency_seconds, exit_code, broker_report
    )


def final_event(all_events: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the session's final result event, or None when it never finished.

    Args:
        all_events: The parsed stream.

    Returns:
        The last event whose type is result, or None when the stream has none.
    """
    return next(
        (
            each_event
            for each_event in reversed(all_events)
            if each_event.get("type") == RESULT_EVENT_TYPE
        ),
        None,
    )


def _tool_reply_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return NEWLINE.join(
            str(each_part.get("text", ""))
            for each_part in content
            if isinstance(each_part, dict)
        )
    return ""


def _assistant_text_turn(block_by_field: Mapping[str, object]) -> dict[str, str]:
    return {"role": "assistant", "content": str(block_by_field.get("text", ""))}


def _tool_call_turn(block_by_field: Mapping[str, object]) -> dict[str, str]:
    return {
        "role": "tool_call",
        "name": str(block_by_field.get("name")),
        "content": json.dumps(block_by_field.get("input"), indent=JSON_INDENT),
    }


def _tool_reply_turn(block_by_field: Mapping[str, object]) -> dict[str, str]:
    return {
        "role": "tool_result",
        "content": _tool_reply_text(block_by_field.get("content"))[:TOOL_RESULT_PREVIEW_LENGTH],
    }


def _event_turns(event_by_field: Mapping[str, object]) -> list[dict[str, str]]:
    message = event_by_field.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), list):
        return []
    turn_builder_by_type = {
        (ASSISTANT_EVENT_TYPE, TEXT_BLOCK_TYPE): _assistant_text_turn,
        (ASSISTANT_EVENT_TYPE, TOOL_USE_BLOCK_TYPE): _tool_call_turn,
        (USER_EVENT_TYPE, TOOL_RESULT_BLOCK_TYPE): _tool_reply_turn,
    }
    all_turns: list[dict[str, str]] = []
    for each_block in message["content"]:
        if not isinstance(each_block, dict):
            continue
        build_turn = turn_builder_by_type.get(
            (event_by_field.get("type"), each_block.get("type"))
        )
        if build_turn is not None:
            all_turns.append(build_turn(each_block))
    return all_turns


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

    Returns:
        The user prompt turn followed by one turn per text, tool_use and
        tool_result block, in stream order.
    """
    all_turns: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    for each_event in all_events:
        all_turns.extend(_event_turns(each_event))
    return all_turns


def served_models(field_by_name: Mapping[str, object]) -> list[str]:
    """Return the model ids the result event bills.

    Args:
        field_by_name: The session's result event.

    Returns:
        The sorted keys of the event's modelUsage map, or an empty list.
    """
    model_usage = field_by_name.get("modelUsage")
    return sorted(model_usage) if isinstance(model_usage, dict) else []
