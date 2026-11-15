"""Reinstall claude-dev-env when a cloud session boots from a stale cache.

A cloud environment runs its setup script (`npx -y claude-dev-env@latest`)
once and caches the filesystem; a later session boots from that cache and
skips the script. A release published after the cache was built never lands,
so the session is missing the commands, rules, and hooks that release ships.

This SessionStart hook closes that gap: it reads the installed version from
the manifest in the Claude config directory (`CLAUDE_CONFIG_DIR` when set,
`~/.claude` otherwise; a relative override anchors to the home directory the
install runs from), asks the npm registry for the current version, and
reinstalls when the two differ. The reinstall hands the installer that same
resolved directory through `CLAUDE_CONFIG_DIR`, so the manifest the installer
writes lands where this hook reads. Both npm calls run from the home directory:
hooks start in the project directory, and inside the repository that develops
this very package, npx resolves the package name to the local workspace
instead of the registry. Local sessions exit at the remote guard. A probe
response that is not a bare semver string (an npmrc ``json=true`` wraps the
version in quotes) reads as a failed probe. Once the module loads, every path exits 0,
so the hook never blocks a session from starting.

A remote start ends silent only when the install is known to be current: the
manifest already matches the registry, or the install exits 0 and the
manifest then matches. Every other end prints one ``systemMessage`` for the
user, named by a ``RefreshOutcome`` member, with the command to run by hand::

    no registry version          -> LOOKUP_FAILED, names @latest
    failed record matches        -> SKIPPED_FAILED_VERSION
    npx missing or not started   -> INSTALLER_DID_NOT_START
    install past the time limit  -> INSTALL_TIMED_OUT
    install exits above 0        -> INSTALL_EXITED, writes the failed record
    install ends on a signal     -> INSTALL_SIGNALLED
    exit 0, manifest still old   -> INSTALL_LEFT_OLD_VERSION
    an exception in the hook     -> HOOK_ERROR

The failed record makes later starts skip that version until the registry
moves to another one. Every other failed end leaves no failed record, so the
next start runs the install again. Before the install starts, the hook writes
the version to an in-progress record, and it removes the record when the
install call returns. A hook killed from outside leaves the record behind. The
next start reads and removes it, and when the manifest then shows another
version it adds ``LAST_REFRESH_UNFINISHED`` to the message.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

try:
    from config.session_start_refresh_constants import (
        CLAUDE_HOME_DIRECTORY_NAME,
        CONFIG_DIR_OVERRIDE_VARIABLE_NAME,
        FAILED_INSTALL_RECORD_FILE_NAME,
        IN_PROGRESS_INSTALL_RECORD_FILE_NAME,
        INSTALL_TIMEOUT_SECONDS,
        LATEST_INSTALL_COMMAND,
        MANIFEST_FILE_NAME,
        MESSAGE_LINE_SEPARATOR,
        NO_INSTALLED_VERSION_TEXT,
        PACKAGE_NAME,
        REGISTRY_PROBE_TIMEOUT_SECONDS,
        REGISTRY_VERSION_PATTERN,
        REMOTE_SESSION_ACTIVE_VALUE,
        REMOTE_SESSION_VARIABLE_NAME,
        RefreshOutcome,
    )
except ImportError:
    sys.modules.pop("config", None)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config.session_start_refresh_constants import (
        CLAUDE_HOME_DIRECTORY_NAME,
        CONFIG_DIR_OVERRIDE_VARIABLE_NAME,
        FAILED_INSTALL_RECORD_FILE_NAME,
        IN_PROGRESS_INSTALL_RECORD_FILE_NAME,
        INSTALL_TIMEOUT_SECONDS,
        LATEST_INSTALL_COMMAND,
        MANIFEST_FILE_NAME,
        MESSAGE_LINE_SEPARATOR,
        NO_INSTALLED_VERSION_TEXT,
        PACKAGE_NAME,
        REGISTRY_PROBE_TIMEOUT_SECONDS,
        REGISTRY_VERSION_PATTERN,
        REMOTE_SESSION_ACTIVE_VALUE,
        REMOTE_SESSION_VARIABLE_NAME,
        RefreshOutcome,
    )

_registry_version_matcher = re.compile(REGISTRY_VERSION_PATTERN)


def claude_config_directory() -> Path:
    override = os.environ.get(CONFIG_DIR_OVERRIDE_VARIABLE_NAME, "").strip()
    if override:
        return (Path.home() / Path(override).expanduser()).resolve()
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME


def read_installed_version() -> str:
    manifest_path = claude_config_directory() / MANIFEST_FILE_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) else ""


def _spawn_tool_from_home(
    tool_path: str,
    all_arguments: list[str],
    output_target: int,
    all_environment_variables: dict[str, str] | None,
) -> subprocess.Popen[str] | None:
    try:
        return subprocess.Popen(
            [tool_path, *all_arguments],
            stdin=subprocess.DEVNULL,
            stdout=output_target,
            stderr=output_target,
            text=True,
            cwd=Path.home(),
            env=all_environment_variables,
            start_new_session=os.name == "posix",
        )
    except OSError:
        return None


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
    else:
        process.kill()
    process.wait()


def _run_tool_from_home(
    tool_name: str,
    all_arguments: list[str],
    timeout_seconds: int,
    *,
    capture: bool,
    all_environment_variables: dict[str, str] | None,
) -> subprocess.CompletedProcess[str] | None:
    tool_path = shutil.which(tool_name)
    if tool_path is None:
        return None
    output_target = subprocess.PIPE if capture else subprocess.DEVNULL
    process = _spawn_tool_from_home(
        tool_path, all_arguments, output_target, all_environment_variables
    )
    if process is None:
        return None
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def read_registry_version() -> str:
    try:
        completed = _run_tool_from_home(
            "npm",
            ["view", PACKAGE_NAME, "version"],
            REGISTRY_PROBE_TIMEOUT_SECONDS,
            capture=True,
            all_environment_variables=None,
        )
    except subprocess.TimeoutExpired:
        return ""
    if completed is None or completed.returncode != 0:
        return ""
    version = completed.stdout.strip()
    return version if _registry_version_matcher.fullmatch(version) else ""


def reinstall(registry_version: str) -> subprocess.CompletedProcess[str] | None:
    environment = os.environ.copy()
    if environment.get(CONFIG_DIR_OVERRIDE_VARIABLE_NAME, "").strip():
        environment[CONFIG_DIR_OVERRIDE_VARIABLE_NAME] = str(claude_config_directory())
    return _run_tool_from_home(
        "npx",
        ["-y", _package_at(registry_version)],
        INSTALL_TIMEOUT_SECONDS,
        capture=False,
        all_environment_variables=environment,
    )


def _package_at(registry_version: str) -> str:
    return PACKAGE_NAME + "@" + registry_version


def _install_command(version: str) -> str:
    return "npx -y " + _package_at(version)


def _record_path(record_file_name: str) -> Path:
    return claude_config_directory() / record_file_name


def _read_record(record_file_name: str) -> str:
    try:
        return _record_path(record_file_name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_record(record_file_name: str, version: str) -> None:
    record_path = _record_path(record_file_name)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(version, encoding="utf-8")


def _remove_record(record_file_name: str) -> None:
    _record_path(record_file_name).unlink(missing_ok=True)


def _installed_version_text() -> str:
    return read_installed_version() or NO_INSTALLED_VERSION_TEXT


def render_message(outcome: RefreshOutcome, **all_fields: object) -> str:
    """Return the line the user sees for one refresh outcome.

    The member's value is the template. Fields a template does not name are
    ignored, so every caller passes the fields it knows::

        render_message(RefreshOutcome.LOOKUP_FAILED)
        -> "claude-dev-env refresh: `npm view claude-dev-env version` gave no
            version, ... run `npx -y claude-dev-env@latest` ..."

    Args:
        outcome: The refresh outcome to describe.
        **all_fields: Values for the template's named fields.

    Returns:
        The formatted message.
    """
    return outcome.value.format(
        latest_install_command=LATEST_INSTALL_COMMAND,
        timeout_seconds=INSTALL_TIMEOUT_SECONDS,
        **all_fields,
    )


def _install_outcome(
    registry_version: str,
) -> tuple[RefreshOutcome | None, dict[str, object]]:
    _write_record(IN_PROGRESS_INSTALL_RECORD_FILE_NAME, registry_version)
    try:
        completed = reinstall(registry_version)
    except subprocess.TimeoutExpired:
        return RefreshOutcome.INSTALL_TIMED_OUT, {}
    finally:
        _remove_record(IN_PROGRESS_INSTALL_RECORD_FILE_NAME)
    if completed is None:
        return RefreshOutcome.INSTALLER_DID_NOT_START, {}
    if completed.returncode > 0:
        _write_record(FAILED_INSTALL_RECORD_FILE_NAME, registry_version)
        return RefreshOutcome.INSTALL_EXITED, {"exit_code": completed.returncode}
    if completed.returncode < 0:
        return RefreshOutcome.INSTALL_SIGNALLED, {
            "signal_number": -completed.returncode
        }
    if read_installed_version() != registry_version:
        return RefreshOutcome.INSTALL_LEFT_OLD_VERSION, {
            "installed_version": _installed_version_text()
        }
    return None, {}


def _refresh_message() -> str:
    registry_version = read_registry_version()
    if not registry_version:
        return render_message(RefreshOutcome.LOOKUP_FAILED)
    if read_installed_version() == registry_version:
        return ""
    version_fields = {
        "version": registry_version,
        "install_command": _install_command(registry_version),
    }
    if _read_record(FAILED_INSTALL_RECORD_FILE_NAME) == registry_version:
        return render_message(RefreshOutcome.SKIPPED_FAILED_VERSION, **version_fields)
    outcome, outcome_fields = _install_outcome(registry_version)
    if outcome is None:
        return ""
    return render_message(outcome, **version_fields, **outcome_fields)


def _unfinished_refresh_message(unfinished_version: str) -> str:
    if not unfinished_version or read_installed_version() == unfinished_version:
        return ""
    return render_message(
        RefreshOutcome.LAST_REFRESH_UNFINISHED,
        version=unfinished_version,
        install_command=_install_command(unfinished_version),
        installed_version=_installed_version_text(),
    )


def _tell_the_user(message: str) -> None:
    sys.stdout.write(json.dumps({"systemMessage": message}) + "\n")
    sys.stdout.flush()


def main() -> None:
    if os.environ.get(REMOTE_SESSION_VARIABLE_NAME) != REMOTE_SESSION_ACTIVE_VALUE:
        return
    unfinished_version = _read_record(IN_PROGRESS_INSTALL_RECORD_FILE_NAME)
    _remove_record(IN_PROGRESS_INSTALL_RECORD_FILE_NAME)
    this_start_message = _refresh_message()
    all_messages = [
        message
        for message in (
            _unfinished_refresh_message(unfinished_version),
            this_start_message,
        )
        if message
    ]
    if all_messages:
        _tell_the_user(MESSAGE_LINE_SEPARATOR.join(all_messages))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        _tell_the_user(
            render_message(RefreshOutcome.HOOK_ERROR, error=type(error).__name__)
        )
