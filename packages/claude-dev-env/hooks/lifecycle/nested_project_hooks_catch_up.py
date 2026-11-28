"""Run the start hooks of checkouts a session attaches after SessionStart.

A cloud thread clones a checkout with add_repo after its SessionStart fired, so
Claude Code never runs that checkout's start hooks. The first later event
starts them in a detached runner and waits a short while for it::

    SessionStart       startup: alpha's start hooks run; alpha.done is written
    add_repo beta
    PreToolUse Bash    beta has no marker: claim beta.claimed, start the runner,
                       wait for beta.done while the gates' timeouts still fit
                       the budget, then run the gates
    runner             beta's start hooks, each with its own timeout;
                       output to beta.log, then beta.done
    next event         beta's log is carried as context, then beta.reported

The markers live in ``~/.claude/state/nested-project-hooks/<session id>/``. The
claim is an exclusive create, so two events that race start one runner. The
done marker is written only after every start hook exits, so a cut-off event
leaves the checkout pending. A claim older than its hooks' timeouts plus a
minute is taken over by the one event that creates the takeover token named
for that claim's modification time. Only a SessionStart with source
``startup`` marks its checkouts done; a ``compact``, ``resume`` or ``clear``
start ran none of their startup hooks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.hook_specific_output_keys import HOOK_SPECIFIC_OUTPUT_KEY
from hooks_constants.nested_project_hooks_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_SESSION_ENV_PATH_PARTS,
    ALL_SHELL_PROGRAM_NAMES,
    ALL_STARTED_STATE_PATH_PARTS,
    CATCH_UP_ENV_FILE_TEMPLATE,
    CATCH_UP_FLAG,
    CATCH_UP_POLL_SECONDS,
    CATCH_UP_SESSION_START_SOURCE,
    CATCH_UP_STALE_SLACK_SECONDS,
    CATCH_UP_WAIT_SECONDS,
    CLAIMED_MARKER_SUFFIX,
    CONTEXT_SECTION_SEPARATOR,
    CWD_KEY,
    DONE_MARKER_SUFFIX,
    FINISHED_NOTE_TEMPLATE,
    HOOK_EVENT_NAME_KEY,
    LOG_FILE_SUFFIX,
    PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE,
    REPORTED_MARKER_SUFFIX,
    RUNNING_NOTE_TEMPLATE,
    SESSION_ENV_FILE_VARIABLE,
    SESSION_ID_KEY,
    SESSION_START_EVENT,
    SETTINGS_ENCODING,
    SHELL_COMMAND_FLAG,
    SOURCE_KEY,
    TAKEOVER_MARKER_TEMPLATE,
)
from hooks_constants.subprocess_window import hidden_window_creation_flags
from lifecycle.nested_project_hooks_discovery import (
    NestedHook,
    collect_nested_hooks,
    find_nested_projects,
)


@dataclass(frozen=True)
class CatchUpReport:
    """One event's context, and the finished checkouts to pass to ``mark_reported``."""

    context: str
    all_finished_checkouts: tuple[Path, ...]


def json_additional_context(all_output_fields: dict[str, object]) -> str:
    """Return the ``additionalContext`` text of one parsed hook output.

    Args:
        all_output_fields: A hook's stdout, parsed as a JSON object.

    Returns:
        The stripped context text, or an empty string when there is none.
    """
    specific_output = all_output_fields.get(HOOK_SPECIFIC_OUTPUT_KEY)
    if not isinstance(specific_output, dict):
        return ""
    context_text = specific_output.get(ADDITIONAL_CONTEXT_KEY)
    return context_text.strip() if isinstance(context_text, str) else ""


def hook_output_context(stdout_text: str) -> str:
    """Return the context a SessionStart hook's stdout carries.

    Args:
        stdout_text: The hook's stdout: a JSON envelope or plain text.

    Returns:
        The envelope's ``additionalContext``, or the stripped plain text.
    """
    try:
        parsed_output = json.loads(stdout_text)
    except json.JSONDecodeError:
        return stdout_text.strip()
    if not isinstance(parsed_output, dict):
        return stdout_text.strip()
    return json_additional_context(parsed_output)


def session_state_directory(session_id: str) -> Path:
    """Return the folder that holds one session's catch-up markers.

    Args:
        session_id: The session id from the hook payload.

    Returns:
        ``~/.claude/state/nested-project-hooks/<session id>``.
    """
    return Path.home().joinpath(*ALL_STARTED_STATE_PATH_PARTS, session_id)


def _marker(session_id: str, checkout: Path, suffix: str) -> Path:
    return session_state_directory(session_id) / (checkout.name + suffix)


def _create_exclusively(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        return False
    with os.fdopen(file_descriptor, "w", encoding=SETTINGS_ENCODING) as marker_file:
        marker_file.write(text)
    return True


def _write_atomically(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = path.with_name(path.name + f".{os.getpid()}.partial")
        partial_path.write_text(text, encoding=SETTINGS_ENCODING)
        os.replace(partial_path, path)
    except OSError:
        return


def _start_hooks(
    session_directory: Path, checkout: Path, forward_siblings: bool
) -> list[NestedHook]:
    all_hooks = collect_nested_hooks(
        session_directory, SESSION_START_EVENT, CATCH_UP_SESSION_START_SOURCE, forward_siblings
    )
    return [each for each in all_hooks if each.project_directory == checkout]


def _allowed_claim_seconds(all_hooks: list[NestedHook]) -> float:
    return sum(each.timeout_seconds for each in all_hooks) + CATCH_UP_STALE_SLACK_SECONDS


def _take_over(claim_path: Path, stale_generation: int) -> bool:
    takeover_path = claim_path.with_name(
        TAKEOVER_MARKER_TEMPLATE.format(claim=claim_path.name, generation=stale_generation)
    )
    if not _create_exclusively(takeover_path, str(os.getpid())):
        return False
    try:
        claim_path.unlink()
    except OSError:
        return False
    return _create_exclusively(claim_path, str(os.getpid()))


def _claim(session_id: str, checkout: Path, all_hooks: list[NestedHook]) -> bool:
    claim_path = _marker(session_id, checkout, CLAIMED_MARKER_SUFFIX)
    if _create_exclusively(claim_path, str(os.getpid())):
        return True
    try:
        claim_status = claim_path.stat()
    except OSError:
        return False
    if time.time() - claim_status.st_mtime <= _allowed_claim_seconds(all_hooks):
        return False
    return _take_over(claim_path, claim_status.st_mtime_ns)


def _spawn_runner(session_directory: Path, session_id: str, checkout: Path) -> None:
    runner_script = Path(__file__).resolve().parent / "nested_project_hooks.py"
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(runner_script),
                CATCH_UP_FLAG,
                str(session_directory),
                session_id,
                str(checkout),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            creationflags=hidden_window_creation_flags(),
        )
    except OSError:
        return


def _wait_for_done(session_id: str, all_checkouts: list[Path], wait_seconds: float) -> None:
    deadline = time.monotonic() + min(CATCH_UP_WAIT_SECONDS, wait_seconds)
    while time.monotonic() < deadline:
        if all(_marker(session_id, each, DONE_MARKER_SUFFIX).exists() for each in all_checkouts):
            return
        time.sleep(CATCH_UP_POLL_SECONDS)


def _report_line(session_id: str, checkout: Path) -> str:
    log_path = _marker(session_id, checkout, LOG_FILE_SUFFIX)
    if not _marker(session_id, checkout, DONE_MARKER_SUFFIX).exists():
        return RUNNING_NOTE_TEMPLATE.format(checkout=checkout.name, log=log_path)
    try:
        log_text = log_path.read_text(encoding=SETTINGS_ENCODING).strip()
    except OSError:
        log_text = ""
    return FINISHED_NOTE_TEMPLATE.format(checkout=checkout.name, log=log_path, output=log_text)


def _valid_session_id(all_payload_fields: dict[str, object]) -> str:
    session_id = all_payload_fields.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return ""
    if os.sep in session_id or "/" in session_id or session_id.startswith("."):
        return ""
    return session_id


def _start_runners(
    session_directory: Path, session_id: str, all_pending: list[Path], forward_siblings: bool
) -> None:
    for each_checkout in all_pending:
        if _marker(session_id, each_checkout, DONE_MARKER_SUFFIX).exists():
            continue
        all_hooks = _start_hooks(session_directory, each_checkout, forward_siblings)
        if _claim(session_id, each_checkout, all_hooks):
            _spawn_runner(session_directory, session_id, each_checkout)


def start_late_checkouts(
    session_directory: Path,
    all_payload_fields: dict[str, object],
    forward_siblings: bool = False,
    wait_seconds: float = CATCH_UP_WAIT_SECONDS,
) -> CatchUpReport:
    """Start the start hooks of late checkouts and report on them.

    Args:
        session_directory: The directory the session started in.
        all_payload_fields: The parsed payload of the current event.
        forward_siblings: Whether a session rooted in a checkout also forwards
            the checkouts beside it.
        wait_seconds: The most time to wait for a runner, capped at
            ``CATCH_UP_WAIT_SECONDS``.

    Returns:
        The report for the current event: each late checkout whose runner
        finished and was not reported yet, with its output, and each one
        still running, with its log path. Empty at SessionStart, where a
        ``startup`` source marks its checkouts done, and for a payload with
        no usable session id.
    """
    session_id = _valid_session_id(all_payload_fields)
    if not session_id:
        return CatchUpReport("", ())
    all_checkouts = find_nested_projects(session_directory, forward_siblings)
    if all_payload_fields.get(HOOK_EVENT_NAME_KEY) == SESSION_START_EVENT:
        if all_payload_fields.get(SOURCE_KEY) == CATCH_UP_SESSION_START_SOURCE:
            _mark_started(all_payload_fields, session_id, all_checkouts)
        return CatchUpReport("", ())
    all_pending = [
        each
        for each in all_checkouts
        if not _marker(session_id, each, REPORTED_MARKER_SUFFIX).exists()
    ]
    if not all_pending:
        return CatchUpReport("", ())
    _start_runners(session_directory, session_id, all_pending, forward_siblings)
    _wait_for_done(session_id, all_pending, wait_seconds)
    all_lines = [_report_line(session_id, each) for each in all_pending]
    all_finished = tuple(
        each for each in all_pending if _marker(session_id, each, DONE_MARKER_SUFFIX).exists()
    )
    return CatchUpReport(
        CONTEXT_SECTION_SEPARATOR.join(each for each in all_lines if each), all_finished
    )


def _mark_started(
    all_payload_fields: dict[str, object], session_id: str, all_checkouts: list[Path]
) -> None:
    for each_checkout in all_checkouts:
        _write_atomically(_marker(session_id, each_checkout, DONE_MARKER_SUFFIX), "")
    mark_reported(all_payload_fields, tuple(all_checkouts))


def mark_reported(
    all_payload_fields: dict[str, object],
    all_checkouts: tuple[Path, ...],
) -> None:
    """Record that the finished checkouts' logs reached Claude Code.

    Args:
        all_payload_fields: The parsed payload of the current event.
        all_checkouts: The checkouts whose logs the event's context carried.
    """
    session_id = _valid_session_id(all_payload_fields)
    if not session_id:
        return
    for each_checkout in all_checkouts:
        _create_exclusively(_marker(session_id, each_checkout, REPORTED_MARKER_SUFFIX), "")


def _shell_program() -> str | None:
    for each_name in ALL_SHELL_PROGRAM_NAMES:
        found_path = shutil.which(each_name)
        if found_path:
            return found_path
    return None


def _runner_environment(session_id: str, checkout: Path) -> dict[str, str]:
    runner_environment = {**os.environ, PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE: str(checkout)}
    if os.environ.get(SESSION_ENV_FILE_VARIABLE):
        return runner_environment
    env_directory = Path.home().joinpath(*ALL_SESSION_ENV_PATH_PARTS, session_id)
    try:
        env_directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return runner_environment
    env_file = env_directory / CATCH_UP_ENV_FILE_TEMPLATE.format(checkout=checkout.name)
    return {**runner_environment, SESSION_ENV_FILE_VARIABLE: str(env_file)}


def _run_one_start_hook(nested_hook: NestedHook, payload_text: str, session_id: str) -> str:
    shell_program = _shell_program()
    if shell_program is None:
        return f"{nested_hook.command!r}: no shell to run it"
    try:
        completed = subprocess.run(
            [shell_program, SHELL_COMMAND_FLAG, nested_hook.command],
            input=payload_text,
            capture_output=True,
            text=True,
            cwd=nested_hook.project_directory,
            env=_runner_environment(session_id, nested_hook.project_directory),
            timeout=nested_hook.timeout_seconds,
            check=False,
            creationflags=hidden_window_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        return f"{nested_hook.command!r}: stopped after {nested_hook.timeout_seconds:.0f} s"
    except OSError as error:
        return f"{nested_hook.command!r}: could not start: {error}"
    all_sections = [hook_output_context(completed.stdout), completed.stderr.strip()]
    if completed.returncode != 0:
        all_sections.append(f"{nested_hook.command!r} exited {completed.returncode}")
    return CONTEXT_SECTION_SEPARATOR.join(each for each in all_sections if each)


def run_catch_up(
    session_directory: Path, session_id: str, checkout: Path, forward_siblings: bool
) -> None:
    """Run one late checkout's start hooks, then write its log and done marker.

    Args:
        session_directory: The directory the session started in.
        session_id: The session id the claim was made under.
        checkout: The checkout whose start hooks run.
        forward_siblings: Whether a session rooted in a checkout also forwards
            the checkouts beside it.
    """
    payload_text = json.dumps(
        {
            SESSION_ID_KEY: session_id,
            HOOK_EVENT_NAME_KEY: SESSION_START_EVENT,
            SOURCE_KEY: CATCH_UP_SESSION_START_SOURCE,
            CWD_KEY: str(session_directory),
        }
    )
    all_outputs = [
        _run_one_start_hook(each_hook, payload_text, session_id)
        for each_hook in _start_hooks(session_directory, checkout, forward_siblings)
    ]
    log_text = CONTEXT_SECTION_SEPARATOR.join(each for each in all_outputs if each)
    _write_atomically(_marker(session_id, checkout, LOG_FILE_SUFFIX), log_text)
    _write_atomically(_marker(session_id, checkout, DONE_MARKER_SUFFIX), "")
