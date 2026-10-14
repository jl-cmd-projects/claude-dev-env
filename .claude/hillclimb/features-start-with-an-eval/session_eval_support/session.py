"""Run one case as a fresh headless Claude Code session through the account broker."""

import contextlib
import ctypes
import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import IO
from dataclasses import dataclass
from pathlib import Path

from session_eval_support.config.constants import (
    ALL_GIT_INIT_COMMANDS,
    ALL_SCORABLE_SUBTYPES,
    ASSISTANT_EVENT_TYPE,
    BROKER_REPORT_FILE_NAME,
    BROKER_SCRIPT,
    BROKER_WAIT_EXIT_CODE,
    DIGEST_LENGTH,
    DIGEST_LENGTH_PREFIX_SIZE,
    FAILURE_BROKER_WAIT,
    FAILURE_MODEL_MISMATCH,
    FAILURE_NO_RESULT,
    FAILURE_TIMEOUT,
    FIXTURE_DIRECTORY,
    CREATE_SUSPENDED_FLAG,
    JOB_ASSIGN_ACCESS,
    JOB_EXIT_CODE,
    KERNEL32_LIBRARY_NAME,
    NT_SUCCESS_STATUS,
    NTDLL_LIBRARY_NAME,
    PYTHON_CACHE_DIRECTORY_NAME,
    PYTHON_SOURCE_GLOB,
    HOOKS_DIRECTORY,
    JSON_INDENT,
    NEWLINE,
    REPOSITORY_ROOT,
    RESULT_EVENT_TYPE,
    RUN_KEY_HARNESS_PREFIX,
    RUN_KEY_INSTALL_PREFIX,
    RUN_KEY_SETTINGS,
    SESSION_SETTING_SOURCES,
    STREAM_FILE_NAME,
    TEST_FILE_PREFIX,
    TEXT_BLOCK_TYPE,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_RESULT_PREVIEW_LENGTH,
    TOOL_USE_BLOCK_TYPE,
    TRACE_FILE_TEMPLATE,
    TRACES_DIRECTORY_NAME,
    USER_EVENT_TYPE,
    WINDOWS_PLATFORM,
    WORKSPACE_PREFIX,
)

if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.append(str(HOOKS_DIRECTORY))

from hooks_constants.windows_filesystem import force_rmtree

logger = logging.getLogger(__name__)


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


def files_digest(bytes_by_target: Mapping[str, bytes]) -> str:
    """Return a short sha256 over a variant's workspace paths and file bytes.

    ::

        files_digest({".claude/rules/index.md": b"Index."}) -> "34db5a63f317"

    Args:
        bytes_by_target: Each workspace path mapped to the bytes installed there.

    Returns:
        The first 12 hex digits of the digest. Each path and its bytes go in
        with their lengths first, so no two different file sets hash alike
        by shifting bytes between fields.
    """
    digest = hashlib.sha256()
    for each_target, each_bytes in sorted(bytes_by_target.items()):
        for each_field in (each_target.encode("utf-8"), each_bytes):
            digest.update(len(each_field).to_bytes(DIGEST_LENGTH_PREFIX_SIZE, "big"))
            digest.update(each_field)
    return digest.hexdigest()[:DIGEST_LENGTH]


def harness_sources(*all_roots: Path) -> list[Path]:
    """Return the Python source files of an eval harness, tests left out.

    ::

        harness_sources(rules_eval_support_dir, run_py)
        -> [.../config/constants.py, .../grading.py, ..., .../run.py]

    Args:
        all_roots: Source files, or directories searched for ``*.py`` files.

    Returns:
        Each source file once, sorted, without ``test_*.py`` files or caches.
    """
    all_files: set[Path] = set()
    for each_root in all_roots:
        all_candidates = [each_root] if each_root.is_file() else each_root.rglob(PYTHON_SOURCE_GLOB)
        all_files.update(
            each_path.resolve()
            for each_path in all_candidates
            if not each_path.name.startswith(TEST_FILE_PREFIX)
            and PYTHON_CACHE_DIRECTORY_NAME not in each_path.parts
        )
    return sorted(all_files)


def _repository_key(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def run_digest(
    bytes_by_target: Mapping[str, bytes],
    setting_by_name: Mapping[str, object],
    all_harness_paths: Iterable[Path],
) -> str:
    """Return the digest that keys resumed rows to everything that shapes a score.

    Args:
        bytes_by_target: The files the workspace installs.
        setting_by_name: The run's session settings, such as model and turn cap.
        all_harness_paths: The harness source files, from harness_sources.

    Returns:
        The files_digest over the installed files, the settings as sorted
        JSON, and each harness file's bytes keyed by its repository path, so
        a change to any of them starts a fresh set of rows.
    """
    return files_digest(
        {
            **{RUN_KEY_INSTALL_PREFIX + each_target: each_bytes for each_target, each_bytes in bytes_by_target.items()},
            RUN_KEY_SETTINGS: json.dumps(setting_by_name, sort_keys=True).encode("utf-8"),
            **{
                RUN_KEY_HARNESS_PREFIX + _repository_key(each_path): each_path.read_bytes()
                for each_path in all_harness_paths
            },
        }
    )


def installed_files(all_installs: list[tuple[str, str]]) -> dict[str, bytes]:
    """Read the files a variant installs once, keyed by workspace path.

    Args:
        all_installs: Pairs of a repository path and its workspace path.

    Returns:
        Each workspace path mapped to its source file's bytes.
    """
    return {
        each_target: (REPOSITORY_ROOT / each_source).read_bytes()
        for each_source, each_target in all_installs
    }


def _fill_workspace(workspace: Path, bytes_by_target: Mapping[str, bytes]) -> None:
    shutil.copytree(FIXTURE_DIRECTORY, workspace, dirs_exist_ok=True)
    for each_target, each_bytes in bytes_by_target.items():
        target_path = workspace / each_target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(each_bytes)
    for each_command in ALL_GIT_INIT_COMMANDS:
        subprocess.run(each_command, cwd=workspace, check=True, capture_output=True)


def prepare_workspace(bytes_by_target: Mapping[str, bytes]) -> Path:
    """Copy the fixture project and the variant's files into a new git workspace.

    Args:
        bytes_by_target: Each workspace path mapped to the bytes installed there.

    Returns:
        The workspace directory, committed on branch main.

    Raises:
        OSError: A copy or write failed; the directory is removed first.
        subprocess.CalledProcessError: A git step failed; the directory is
            removed first.
    """
    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    try:
        _fill_workspace(workspace, bytes_by_target)
    except (OSError, subprocess.CalledProcessError):
        remove_workspace(workspace)
        raise
    return workspace


def remove_workspace(workspace: Path) -> None:
    """Delete a workspace once its session is read, read-only git objects included.

    Args:
        workspace: A directory from prepare_workspace.
    """
    force_rmtree(str(workspace))


def _read_events(stream_path: Path) -> list[dict[str, object]]:
    all_events: list[dict[str, object]] = []
    if not stream_path.is_file():
        return all_events
    for each_line in stream_path.read_text(
        encoding="utf-8", errors="replace"
    ).split(NEWLINE):
        try:
            each_event = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if isinstance(each_event, dict):
            all_events.append(each_event)
    return all_events


def session_words(settings: SessionSettings) -> list[str]:
    """Return the headless claude command for one session, before any launcher wraps it.

    The prompt goes on standard input, so no launcher shim reparses it.

    Args:
        settings: The model, effort and turn cap.

    Returns:
        The claude command and its arguments.
    """
    return [
        "claude",
        "-p",
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


def brokered_words(report_path: Path, all_claude_words: list[str]) -> list[str]:
    """Return the command that runs a claude command through the account broker.

    ::

        brokered_words(r, ["claude", "-p", "hi"])
        -> [python, account_broker.py, "run", "--product", "claude", "--report", r, "--", "claude", "-p", "hi"]

    Args:
        report_path: Where the broker writes its report.
        all_claude_words: The claude command and its arguments.

    Returns:
        The full argument list for subprocess.
    """
    return [
        sys.executable,
        str(BROKER_SCRIPT),
        "run",
        "--product",
        "claude",
        "--report",
        str(report_path),
        "--",
        *all_claude_words,
    ]


def _read_broker_report(report_path: Path) -> dict[str, object]:
    if not report_path.is_file():
        return {}
    try:
        loaded = json.loads(report_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _windows_kernel() -> ctypes.CDLL:
    kernel = ctypes.WinDLL(KERNEL32_LIBRARY_NAME, use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.OpenProcess.restype = ctypes.c_void_p
    return kernel


def _windows_native() -> ctypes.CDLL:
    return ctypes.WinDLL(NTDLL_LIBRARY_NAME)


def _popen_options() -> dict[str, object]:
    if sys.platform == WINDOWS_PLATFORM:
        return {"creationflags": CREATE_SUSPENDED_FLAG}
    return {"start_new_session": True}


def _assigned_job(kernel: ctypes.CDLL, process_handle: int | None) -> int | None:
    job_handle = kernel.CreateJobObjectW(None, None)
    if job_handle and process_handle and kernel.AssignProcessToJobObject(ctypes.c_void_p(job_handle), ctypes.c_void_p(process_handle)):
        return job_handle
    if job_handle:
        kernel.CloseHandle(ctypes.c_void_p(job_handle))
    return None


def _resume_or_terminate(kernel: ctypes.CDLL, process_handle: int, pid: int) -> None:
    resume_status = _windows_native().NtResumeProcess(ctypes.c_void_p(process_handle))
    if resume_status != NT_SUCCESS_STATUS:
        logger.warning("resuming pid %d failed with status %#x, so it is terminated", pid, resume_status)
        kernel.TerminateProcess(ctypes.c_void_p(process_handle), JOB_EXIT_CODE)


def _join_new_job(pid: int) -> int | None:
    kernel = _windows_kernel()
    process_handle = kernel.OpenProcess(JOB_ASSIGN_ACCESS, False, pid)
    job_handle = _assigned_job(kernel, process_handle)
    if job_handle is None:
        logger.warning("no job object for pid %d, so its children may outlive it", pid)
    if process_handle:
        _resume_or_terminate(kernel, process_handle, pid)
        kernel.CloseHandle(ctypes.c_void_p(process_handle))
    return job_handle


@dataclass(frozen=True)
class _StartedCommand:
    process: subprocess.Popen[bytes]
    job_handle: int | None


def _end_job(job_handle: int) -> None:
    kernel = _windows_kernel()
    kernel.TerminateJobObject(ctypes.c_void_p(job_handle), JOB_EXIT_CODE)
    kernel.CloseHandle(ctypes.c_void_p(job_handle))


def _kill_without_job(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == WINDOWS_PLATFORM:
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)


def _stop_group(command: _StartedCommand) -> None:
    if command.job_handle is not None:
        _end_job(command.job_handle)
    else:
        with contextlib.suppress(OSError):
            _kill_without_job(command.process)
    command.process.wait()


def _write_input(process: subprocess.Popen[bytes], input_bytes: bytes) -> None:
    try:
        process.stdin.write(input_bytes)
    except OSError as error:
        logger.warning("standard input to pid %d failed: %s", process.pid, error)
    finally:
        with contextlib.suppress(OSError):
            process.stdin.close()


def _start_with_input(
    all_command_words: list[str],
    working_directory: Path,
    capture_file: IO[bytes] | IO[str],
    input_bytes: bytes,
) -> _StartedCommand:
    process = subprocess.Popen(
        all_command_words,
        cwd=working_directory,
        stdin=subprocess.PIPE,
        stdout=capture_file,
        stderr=subprocess.DEVNULL,
        **_popen_options(),
    )
    is_windows = sys.platform == WINDOWS_PLATFORM
    command = _StartedCommand(process, _join_new_job(process.pid) if is_windows else None)
    threading.Thread(target=_write_input, args=(process, input_bytes), daemon=True).start()
    return command


def run_until_timeout(
    all_command_words: list[str],
    working_directory: Path,
    capture_file: IO[bytes] | IO[str],
    timeout_seconds: int,
    input_bytes: bytes,
) -> int | None:
    """Run a command with input on standard input, then stop what it started.

    ::

        ignores 10 MB of input, timeout 2s    -> None after about 2s
        leaves a background child and exits   -> 0, child stopped via group or job

    Args:
        all_command_words: The command and its arguments.
        working_directory: The command's working directory.
        capture_file: Where standard output goes.
        timeout_seconds: The wall-clock ceiling.
        input_bytes: Standard input, written from its own thread.

    Returns:
        The exit code, or None when the command timed out.
    """
    command = _start_with_input(all_command_words, working_directory, capture_file, input_bytes)
    with contextlib.suppress(subprocess.TimeoutExpired):
        command.process.wait(timeout=timeout_seconds)
    exit_code = command.process.returncode
    _stop_group(command)
    return exit_code


def _run_in_capture(
    capture_directory: Path,
    workspace: Path,
    prompt: str,
    settings: SessionSettings,
    launch: Callable[[Path, list[str]], list[str]],
) -> SessionRun:
    stream_path = capture_directory / STREAM_FILE_NAME
    all_command_words = launch(
        capture_directory / BROKER_REPORT_FILE_NAME, session_words(settings)
    )
    started = time.monotonic()
    with stream_path.open("wb") as stream_file:
        exit_code = run_until_timeout(
            all_command_words,
            workspace,
            stream_file,
            settings.timeout_seconds,
            prompt.encode("utf-8"),
        )
    latency_seconds = time.monotonic() - started
    return SessionRun(
        _read_events(stream_path),
        latency_seconds,
        exit_code,
        _read_broker_report(capture_directory / BROKER_REPORT_FILE_NAME),
    )


def run_session(
    workspace: Path,
    prompt: str,
    settings: SessionSettings,
    launch: Callable[[Path, list[str]], list[str]] = brokered_words,
) -> SessionRun:
    """Run the prompt as one headless session in the workspace and read its stream.

    The stream and the launcher's report land in a temporary sibling
    directory that is removed once both are read.

    Args:
        workspace: The prepared workspace, used as the session's directory.
        prompt: The case's ask, sent on standard input as the first user turn.
        settings: The model, effort, turn cap and wall-clock ceiling.
        launch: Builds the command from the report path and the claude words.

    Returns:
        The stream, latency, exit code (None on timeout) and broker report.
    """
    with tempfile.TemporaryDirectory(
        prefix=workspace.name + "-out-", ignore_cleanup_errors=True
    ) as capture_name:
        return _run_in_capture(Path(capture_name), workspace, prompt, settings, launch)


def unscorable(
    session: SessionRun, settings: SessionSettings
) -> tuple[str, object] | None:
    """Return the failure class and detail for a session that cannot be graded.

    Args:
        session: What the session left behind.
        settings: The settings the session ran with.

    Returns:
        The failure class and its detail, or None when the session is scorable.
    """
    if session.exit_code == BROKER_WAIT_EXIT_CODE:
        return FAILURE_BROKER_WAIT, session.broker_report.get("final_decision")
    if session.exit_code is None:
        return FAILURE_TIMEOUT, settings.timeout_seconds
    final = final_event(session.all_events)
    if final is None or final.get("subtype") not in ALL_SCORABLE_SUBTYPES:
        return FAILURE_NO_RESULT, None if final is None else final.get("subtype")
    all_served = served_models(final)
    if not any(each_model.startswith(settings.model) for each_model in all_served):
        return FAILURE_MODEL_MISMATCH, all_served
    return None


def write_trace(
    case_by_field: Mapping[str, str], rep: int, variant_directory: Path, session: SessionRun
) -> None:
    """Write one session's trace turns under the variant's traces folder.

    Args:
        case_by_field: The case, with its ``id`` and ``prompt``.
        rep: The repetition number.
        variant_directory: The variant's results folder.
        session: What the session left behind.
    """
    trace_path = (
        variant_directory
        / TRACES_DIRECTORY_NAME
        / TRACE_FILE_TEMPLATE.format(case_id=case_by_field["id"], rep=rep)
    )
    trace_path.write_text(
        json.dumps(
            trace_turns(case_by_field["prompt"], session.all_events),
            indent=JSON_INDENT,
        ),
        encoding="utf-8",
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
