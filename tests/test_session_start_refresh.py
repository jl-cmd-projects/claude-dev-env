"""Behavior checks for the cloud SessionStart refresh hook.

The behavior checks run `.claude/hooks/session_start_refresh.py` as a
subprocess against a sandbox home directory, with fake `npm` and `npx`
executables on `PATH` that record their arguments to a log file. The fake
`npx` writes the manifest for the version it was asked for when it exits 0,
as the installer does. Environment switches make it sleep, end on a signal,
exit above 0, or leave the manifest alone. The assertions read that log, the
JSON `systemMessage` on stdout, and the records beside the manifest: a
refresh run shows an `npx -y claude-dev-env@<version>` line, a quiet run
shows none. Two static checks
bind the `.claude/settings.json` registration to the hook: the registered
command names the script on disk, and the probe and install budgets stay
inside the registered timeout.
"""

import importlib.util
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
HOOK_SCRIPT = REPOSITORY_ROOT / ".claude" / "hooks" / "session_start_refresh.py"
PYTHON_SCRIPT_LAUNCHER = (
    REPOSITORY_ROOT / ".claude" / "hooks" / "python_script_launcher.js"
)


def _refresh_constants() -> ModuleType:
    constants_path = (
        REPOSITORY_ROOT
        / ".claude"
        / "hooks"
        / "config"
        / "session_start_refresh_constants.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_start_refresh_constants", constants_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REFRESH_CONSTANTS = _refresh_constants()
MANIFEST_FILE_NAME: str = REFRESH_CONSTANTS.MANIFEST_FILE_NAME


def _session_start_registration() -> dict[str, object]:
    settings = json.loads(
        (REPOSITORY_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    all_entries = [
        entry
        for group in settings["hooks"]["SessionStart"]
        for entry in group["hooks"]
    ]
    [entry] = [
        entry
        for entry in all_entries
        if HOOK_SCRIPT.name in str(entry.get("command", ""))
    ]
    return entry


SESSION_START_REGISTRATION = _session_start_registration()


def should_register_a_hook_command_that_names_the_existing_script() -> None:
    command = SESSION_START_REGISTRATION["command"]
    assert isinstance(command, str)
    assert HOOK_SCRIPT.name in command
    assert HOOK_SCRIPT.is_file()


def should_use_the_node_launcher_for_the_session_start_registration() -> None:
    command = SESSION_START_REGISTRATION["command"]
    assert isinstance(command, str)
    assert command == (
        "node .claude/hooks/python_script_launcher.js "
        ".claude/hooks/session_start_refresh.py"
    )


def should_run_a_python_script_with_arguments_and_exit_status(
    tmp_path: Path,
) -> None:
    python_script = tmp_path / "echo_arguments.py"
    python_script.write_text(
        "import sys\n"
        "print('|'.join(sys.argv[1:]))\n"
        "sys.exit(23)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            "node",
            str(PYTHON_SCRIPT_LAUNCHER),
            str(python_script),
            "first-argument",
            "second-argument",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 23
    assert completed.stdout.strip() == "first-argument|second-argument"


def should_keep_the_subprocess_budgets_inside_the_registered_timeout() -> None:
    registered_timeout = SESSION_START_REGISTRATION["timeout"]
    assert isinstance(registered_timeout, int)
    subprocess_budget = (
        REFRESH_CONSTANTS.REGISTRY_PROBE_TIMEOUT_SECONDS
        + REFRESH_CONSTANTS.INSTALL_TIMEOUT_SECONDS
    )
    assert subprocess_budget < registered_timeout

POSIX_NPM_SHIM = """#!/bin/bash
printf 'npm %s cwd=%s\\n' "$*" "$PWD" >> "$FAKE_TOOL_LOG"
if [ -n "${FAKE_NPM_FAILURE:-}" ]; then
  exit 1
fi
printf '%s\\n' "$FAKE_NPM_VERSION"
"""

POSIX_NPX_SHIM = """#!/bin/bash
printf 'npx %s cfg=%s cwd=%s\\n' "$*" "$CLAUDE_CONFIG_DIR" "$PWD" >> "$FAKE_TOOL_LOG"
if [ -n "${FAKE_NPX_SLEEP:-}" ]; then
  printf '%s' "$$" > "$FAKE_TOOL_LOG.npx-pid"
  exec sleep "$FAKE_NPX_SLEEP"
fi
if [ -n "${FAKE_NPX_SIGNAL:-}" ]; then
  kill -KILL $$
fi
if [ "${FAKE_NPX_EXIT:-0}" = 0 ] && [ -z "${FAKE_NPX_LEAVES_MANIFEST:-}" ]; then
  config_directory="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  mkdir -p "$config_directory"
  printf '{"version": "%s"}' "${2#claude-dev-env@}" > "$config_directory/.claude-dev-env-manifest.json"
fi
exit "${FAKE_NPX_EXIT:-0}"
"""

WINDOWS_NPM_SHIM = """@echo off
echo npm %* cwd=%CD% >> "%FAKE_TOOL_LOG%"
if defined FAKE_NPM_FAILURE exit /b 1
echo %FAKE_NPM_VERSION%
"""

WINDOWS_NPX_SHIM = """@echo off
echo npx %* cfg=%CLAUDE_CONFIG_DIR% cwd=%CD% >> "%FAKE_TOOL_LOG%"
if defined FAKE_NPX_EXIT exit /b %FAKE_NPX_EXIT%
set "package=%2"
set "config_directory=%CLAUDE_CONFIG_DIR%"
if not defined config_directory set "config_directory=%USERPROFILE%\\.claude"
if not exist "%config_directory%" mkdir "%config_directory%"
echo {"version": "%package:claude-dev-env@=%"}> "%config_directory%\\.claude-dev-env-manifest.json"
"""


def _write_probe_shims(shim_directory: Path) -> None:
    if os.name == "nt":
        (shim_directory / "npm.cmd").write_text(WINDOWS_NPM_SHIM, encoding="utf-8")
        (shim_directory / "npx.cmd").write_text(WINDOWS_NPX_SHIM, encoding="utf-8")
        return
    for shim_name, shim_body in (("npm", POSIX_NPM_SHIM), ("npx", POSIX_NPX_SHIM)):
        shim_path = shim_directory / shim_name
        shim_path.write_text(shim_body, encoding="utf-8")
        shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR)


def _write_manifest(directory: Path, version: str) -> None:
    (directory / MANIFEST_FILE_NAME).write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )


def _seed_sandbox(
    sandbox: Path,
    installed_version: str | None,
    config_dir_version: str | None,
) -> None:
    shim_directory = sandbox / "bin"
    shim_directory.mkdir()
    _write_probe_shims(shim_directory)
    (sandbox / "tool-log.txt").write_text("", encoding="utf-8")
    (sandbox / "home" / ".claude").mkdir(parents=True)
    if installed_version is not None:
        _write_manifest(sandbox / "home" / ".claude", installed_version)
    if config_dir_version is not None:
        (sandbox / "config-override").mkdir()
        _write_manifest(sandbox / "config-override", config_dir_version)


def _hook_environment(
    sandbox: Path,
    *,
    remote: bool,
    registry_version: str,
    registry_failure: bool,
    config_dir_version: str | None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("CLAUDE_CODE_REMOTE", None)
    environment.pop("CLAUDE_CONFIG_DIR", None)
    if remote:
        environment["CLAUDE_CODE_REMOTE"] = "true"
    if config_dir_version is not None:
        environment["CLAUDE_CONFIG_DIR"] = str(sandbox / "config-override")
    environment["PATH"] = os.pathsep.join(
        [str(sandbox / "bin"), environment.get("PATH", "")]
    )
    environment["HOME"] = str(sandbox / "home")
    environment["USERPROFILE"] = str(sandbox / "home")
    environment["FAKE_TOOL_LOG"] = str(sandbox / "tool-log.txt")
    environment["FAKE_NPM_VERSION"] = registry_version
    if registry_failure:
        environment["FAKE_NPM_FAILURE"] = "1"
    return environment


def _run_hook_process(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        env=environment, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def _run_hook_script(sandbox: Path, environment: dict[str, str]) -> str:
    _run_hook_process(environment)
    return (sandbox / "tool-log.txt").read_text(encoding="utf-8")


def run_hook(
    sandbox: Path,
    *,
    remote: bool,
    installed_version: str | None,
    registry_version: str,
    registry_failure: bool = False,
    config_dir_version: str | None = None,
) -> str:
    _seed_sandbox(sandbox, installed_version, config_dir_version)
    environment = _hook_environment(
        sandbox,
        remote=remote,
        registry_version=registry_version,
        registry_failure=registry_failure,
        config_dir_version=config_dir_version,
    )
    return _run_hook_script(sandbox, environment)


def should_stay_quiet_when_the_remote_flag_is_absent(tmp_path: Path) -> None:
    tool_log = run_hook(
        tmp_path, remote=False, installed_version="2.9.0", registry_version="2.12.0"
    )
    assert tool_log == ""


def should_reinstall_from_the_home_directory_when_the_registry_is_ahead(
    tmp_path: Path,
) -> None:
    tool_log = run_hook(
        tmp_path, remote=True, installed_version="2.9.0", registry_version="2.12.0"
    )
    assert "npm view claude-dev-env version" in tool_log
    assert "npx -y claude-dev-env@2.12.0" in tool_log
    logged_lines = tool_log.strip().splitlines()
    assert len(logged_lines) == 2, tool_log
    for logged_line in logged_lines:
        assert logged_line.rstrip().endswith("cwd=" + str(tmp_path / "home")), (
            logged_line
        )


def should_leave_a_current_install_in_place(tmp_path: Path) -> None:
    tool_log = run_hook(
        tmp_path, remote=True, installed_version="2.12.0", registry_version="2.12.0"
    )
    assert "npm view claude-dev-env version" in tool_log
    assert "npx -y" not in tool_log


def should_fail_open_when_the_registry_probe_fails(tmp_path: Path) -> None:
    tool_log = run_hook(
        tmp_path,
        remote=True,
        installed_version="2.9.0",
        registry_version="2.12.0",
        registry_failure=True,
    )
    assert "npx -y" not in tool_log


def should_stay_quiet_when_the_registry_output_is_not_a_version(
    tmp_path: Path,
) -> None:
    tool_log = run_hook(
        tmp_path,
        remote=True,
        installed_version="2.9.0",
        registry_version='"2.12.0"',
    )
    assert "npx -y" not in tool_log


def should_reinstall_on_a_prerelease_and_build_registry_version(
    tmp_path: Path,
) -> None:
    tool_log = run_hook(
        tmp_path,
        remote=True,
        installed_version="2.9.0",
        registry_version="2.12.0-rc.1+build.5",
    )
    assert "npx -y claude-dev-env@2.12.0-rc.1+build.5" in tool_log


def should_reinstall_when_no_manifest_is_present(tmp_path: Path) -> None:
    tool_log = run_hook(
        tmp_path, remote=True, installed_version=None, registry_version="2.12.0"
    )
    assert "npx -y claude-dev-env@2.12.0" in tool_log


def should_exit_zero_and_reinstall_when_the_manifest_is_not_an_object(
    tmp_path: Path,
) -> None:
    _seed_sandbox(tmp_path, None, None)
    (tmp_path / "home" / ".claude" / MANIFEST_FILE_NAME).write_text(
        "[1, 2]", encoding="utf-8"
    )
    environment = _hook_environment(
        tmp_path,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    tool_log = _run_hook_script(tmp_path, environment)
    assert "npx -y claude-dev-env@2.12.0" in tool_log


def should_pass_the_resolved_config_dir_to_the_reinstall(tmp_path: Path) -> None:
    _seed_sandbox(tmp_path, None, None)
    environment = _hook_environment(
        tmp_path,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    environment["CLAUDE_CONFIG_DIR"] = "~/profile"
    tool_log = _run_hook_script(tmp_path, environment)
    resolved_config_dir = tmp_path / "home" / "profile"
    assert "cfg=" + str(resolved_config_dir) + " " in tool_log, tool_log


def should_read_the_manifest_from_a_config_dir_override(tmp_path: Path) -> None:
    tool_log = run_hook(
        tmp_path,
        remote=True,
        installed_version=None,
        registry_version="2.12.0",
        config_dir_version="2.12.0",
    )
    assert "npm view claude-dev-env version" in tool_log
    assert "npx -y" not in tool_log


def should_import_constants_when_the_hook_directory_is_off_sys_path(
    tmp_path: Path,
) -> None:
    _seed_sandbox(tmp_path, "2.12.0", None)
    environment = _hook_environment(
        tmp_path,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    environment["PYTHONSAFEPATH"] = "1"
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    tool_log = _run_hook_script(tmp_path, environment)
    assert "npm view claude-dev-env version" in tool_log
    assert "npx -y" not in tool_log


def should_anchor_a_relative_config_dir_override_to_the_home_directory(
    tmp_path: Path,
) -> None:
    _seed_sandbox(tmp_path, None, None)
    profile_directory = tmp_path / "home" / "profile"
    profile_directory.mkdir()
    _write_manifest(profile_directory, "2.12.0")
    environment = _hook_environment(
        tmp_path,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    environment["CLAUDE_CONFIG_DIR"] = "profile"
    tool_log = _run_hook_script(tmp_path, environment)
    assert "npm view claude-dev-env version" in tool_log
    assert "npx -y" not in tool_log


def _failing_install_environment(sandbox: Path) -> dict[str, str]:
    _seed_sandbox(sandbox, "2.9.0", None)
    environment = _hook_environment(
        sandbox,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    environment["FAKE_NPX_EXIT"] = "1"
    return environment


def _user_message(completed: subprocess.CompletedProcess[str]) -> str:
    message = json.loads(completed.stdout)["systemMessage"]
    assert isinstance(message, str)
    return message


def should_tell_the_user_the_exit_code_when_the_install_fails(tmp_path: Path) -> None:
    completed = _run_hook_process(_failing_install_environment(tmp_path))
    message = _user_message(completed)
    assert "npx -y claude-dev-env@2.12.0" in message
    assert "exit code 1" in message


def should_skip_a_version_whose_install_failed_at_an_earlier_start(
    tmp_path: Path,
) -> None:
    environment = _failing_install_environment(tmp_path)
    _run_hook_process(environment)
    second_start = _run_hook_process(environment)
    tool_log = (tmp_path / "tool-log.txt").read_text(encoding="utf-8")
    assert tool_log.count("npx -y claude-dev-env@2.12.0") == 1, tool_log
    assert "npx -y claude-dev-env@2.12.0" in _user_message(second_start)


def should_install_the_next_release_quietly_after_a_failed_one(
    tmp_path: Path,
) -> None:
    environment = _failing_install_environment(tmp_path)
    _run_hook_process(environment)
    environment["FAKE_NPM_VERSION"] = "2.13.0"
    environment.pop("FAKE_NPX_EXIT")
    next_release_start = _run_hook_process(environment)
    tool_log = (tmp_path / "tool-log.txt").read_text(encoding="utf-8")
    assert "npx -y claude-dev-env@2.13.0" in tool_log
    assert next_release_start.stdout == ""


def should_skip_a_failed_version_when_the_config_dir_does_not_exist_yet(
    tmp_path: Path,
) -> None:
    environment = _failing_install_environment(tmp_path)
    environment["CLAUDE_CONFIG_DIR"] = "~/profile"
    _run_hook_process(environment)
    second_start = _run_hook_process(environment)
    tool_log = (tmp_path / "tool-log.txt").read_text(encoding="utf-8")
    assert tool_log.count("npx -y claude-dev-env@2.12.0") == 1, tool_log
    assert "skipped 2.12.0" in _user_message(second_start)
IN_PROGRESS_RECORD_NAME = ".claude-dev-env-refresh-in-progress"
FAILED_RECORD_NAME = ".claude-dev-env-refresh-failed-version"
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="the stub npx is a bash script")


def _stale_install_environment(sandbox: Path) -> dict[str, str]:
    _seed_sandbox(sandbox, "2.9.0", None)
    return _hook_environment(
        sandbox,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )


def _config_directory(sandbox: Path) -> Path:
    return sandbox / "home" / ".claude"


def _hook_copy_with_install_limit(sandbox: Path, limit_seconds: int) -> Path:
    hooks_copy = sandbox / "hooks-copy"
    shutil.copytree(
        HOOK_SCRIPT.parent,
        hooks_copy,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    constants_path = hooks_copy / "config" / "session_start_refresh_constants.py"
    constants_text = constants_path.read_text(encoding="utf-8")
    lowered_text = constants_text.replace(
        "INSTALL_TIMEOUT_SECONDS = 570",
        f"INSTALL_TIMEOUT_SECONDS = {limit_seconds}",
    )
    assert lowered_text != constants_text
    constants_path.write_text(lowered_text, encoding="utf-8")
    return hooks_copy / HOOK_SCRIPT.name


def _process_is_gone(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return True
    return False


def should_tell_the_user_when_the_version_lookup_fails(tmp_path: Path) -> None:
    environment = _stale_install_environment(tmp_path)
    environment["FAKE_NPM_FAILURE"] = "1"
    message = _user_message(_run_hook_process(environment))
    assert "gave no version" in message
    assert "npx -y claude-dev-env@latest" in message


@POSIX_ONLY
def should_tell_the_user_when_npx_cannot_be_found(tmp_path: Path) -> None:
    environment = _stale_install_environment(tmp_path)
    npm_only_directory = tmp_path / "bin-npm-only"
    npm_only_directory.mkdir()
    shutil.copy2(tmp_path / "bin" / "npm", npm_only_directory / "npm")
    environment["PATH"] = str(npm_only_directory)
    message = _user_message(_run_hook_process(environment))
    assert "npx was not found on PATH or could not start" in message
    assert "npx -y claude-dev-env@2.12.0" in message
    assert not (_config_directory(tmp_path) / FAILED_RECORD_NAME).exists()


@POSIX_ONLY
def should_tell_the_user_when_the_install_runs_past_the_time_limit(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    environment["FAKE_NPX_SLEEP"] = "30"
    hook_copy = _hook_copy_with_install_limit(tmp_path, 1)
    completed = subprocess.run(
        [sys.executable, str(hook_copy)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    message = _user_message(completed)
    assert "ran past 1 seconds and was stopped" in message
    assert "manifest shows 2.9.0" in message
    assert "booted with" not in message
    assert "npx -y claude-dev-env@2.12.0" in message
    npx_process_id = int((tmp_path / "tool-log.txt.npx-pid").read_text())
    assert _process_is_gone(npx_process_id)
    assert _all_in_progress_records(tmp_path) == []
    assert not (_config_directory(tmp_path) / FAILED_RECORD_NAME).exists()


@POSIX_ONLY
def should_tell_the_user_when_the_install_ends_on_a_signal(tmp_path: Path) -> None:
    environment = _stale_install_environment(tmp_path)
    environment["FAKE_NPX_SIGNAL"] = "1"
    message = _user_message(_run_hook_process(environment))
    assert "stopped by signal 9" in message
    assert "manifest shows 2.9.0" in message
    assert "booted with" not in message
    assert "npx -y claude-dev-env@2.12.0" in message


def should_tell_the_user_when_the_install_exits_zero_and_leaves_the_old_version(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    environment["FAKE_NPX_LEAVES_MANIFEST"] = "1"
    message = _user_message(_run_hook_process(environment))
    assert "exited 0, but the manifest shows 2.9.0 instead of 2.12.0" in message


def _start_a_refresh_that_waits_in_its_install(
    sandbox: Path, environment: dict[str, str]
) -> subprocess.Popen[str]:
    npx_pid_path = sandbox / "tool-log.txt.npx-pid"
    running_start = subprocess.Popen(
        [sys.executable, str(HOOK_SCRIPT)],
        env={**environment, "FAKE_NPX_SLEEP": "30"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while not (npx_pid_path.exists() and npx_pid_path.read_text()):
        assert time.monotonic() < deadline, "the stub npx never started"
        time.sleep(0.05)
    return running_start


def _kill_the_refresh(sandbox: Path, running_start: subprocess.Popen[str]) -> str:
    running_start.kill()
    killed_stdout, _ = running_start.communicate(timeout=10)
    os.killpg(int((sandbox / "tool-log.txt.npx-pid").read_text()), signal.SIGKILL)
    return killed_stdout


def _all_in_progress_records(sandbox: Path) -> list[Path]:
    return sorted(_config_directory(sandbox).glob(IN_PROGRESS_RECORD_NAME + "*"))


@POSIX_ONLY
def should_tell_the_user_at_the_next_start_when_the_last_refresh_did_not_finish(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    first_start = _start_a_refresh_that_waits_in_its_install(tmp_path, environment)
    assert _kill_the_refresh(tmp_path, first_start) == ""
    [in_progress_record] = _all_in_progress_records(tmp_path)
    assert json.loads(in_progress_record.read_text(encoding="utf-8"))["version"] == (
        "2.12.0"
    )
    environment["FAKE_NPM_FAILURE"] = "1"
    message = _user_message(_run_hook_process(environment))
    unfinished_line, lookup_line = message.splitlines()
    assert "stopped at an earlier session start before its install of 2.12.0" in (
        unfinished_line
    )
    assert "manifest shows 2.9.0" in unfinished_line
    assert "npx -y claude-dev-env@2.12.0" in unfinished_line
    assert "gave no version" in lookup_line
    assert _all_in_progress_records(tmp_path) == []


@POSIX_ONLY
def should_stay_quiet_about_a_stopped_refresh_once_a_later_install_passes_its_version(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    first_start = _start_a_refresh_that_waits_in_its_install(tmp_path, environment)
    _kill_the_refresh(tmp_path, first_start)
    environment["FAKE_NPM_VERSION"] = "2.13.0"
    next_start = _run_hook_process(environment)
    tool_log = (tmp_path / "tool-log.txt").read_text(encoding="utf-8")
    assert "npx -y claude-dev-env@2.13.0" in tool_log
    assert next_start.stdout == ""
    assert _all_in_progress_records(tmp_path) == []


@POSIX_ONLY
def should_not_call_a_refresh_that_is_still_running_stopped(tmp_path: Path) -> None:
    environment = _stale_install_environment(tmp_path)
    running_start = _start_a_refresh_that_waits_in_its_install(tmp_path, environment)
    try:
        overlapping_start = _run_hook_process({**environment, "FAKE_NPM_FAILURE": "1"})
    finally:
        _kill_the_refresh(tmp_path, running_start)
    [lookup_line] = _user_message(overlapping_start).splitlines()
    assert "gave no version" in lookup_line


@POSIX_ONLY
def should_tell_the_user_about_a_refresh_stopped_after_an_overlapping_start_ended(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    running_start = _start_a_refresh_that_waits_in_its_install(tmp_path, environment)
    try:
        overlapping_start = _run_hook_process({**environment, "FAKE_NPX_EXIT": "1"})
    finally:
        _kill_the_refresh(tmp_path, running_start)
    assert "exit code 1" in _user_message(overlapping_start)
    message = _user_message(_run_hook_process({**environment, "FAKE_NPM_FAILURE": "1"}))
    assert "stopped at an earlier session start before its install of 2.12.0" in (
        message
    )


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs /proc")
def should_tell_the_user_about_a_refresh_whose_process_is_a_zombie(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    exited_child = subprocess.Popen([sys.executable, "-c", "pass"])
    child_stat_path = Path(f"/proc/{exited_child.pid}/stat")
    deadline = time.monotonic() + 10
    while child_stat_path.read_text().rsplit(")", 1)[-1].split()[0] != "Z":
        assert time.monotonic() < deadline, "the child never exited"
        time.sleep(0.05)
    (_config_directory(tmp_path) / f"{IN_PROGRESS_RECORD_NAME}.{exited_child.pid}").write_text(
        json.dumps(
            {"version": "2.12.0", "pid": exited_child.pid, "started_at": time.time()}
        ),
        encoding="utf-8",
    )
    environment["FAKE_NPM_FAILURE"] = "1"
    try:
        message = _user_message(_run_hook_process(environment))
    finally:
        exited_child.wait()
    assert "stopped at an earlier session start before its install of 2.12.0 ended" in (
        message
    )


def should_tell_the_user_about_a_record_older_than_any_refresh_run(
    tmp_path: Path,
) -> None:
    environment = _stale_install_environment(tmp_path)
    (_config_directory(tmp_path) / IN_PROGRESS_RECORD_NAME).write_text(
        json.dumps(
            {"version": "2.12.0", "pid": os.getpid(), "started_at": time.time() - 86400}
        ),
        encoding="utf-8",
    )
    environment["FAKE_NPM_FAILURE"] = "1"
    message = _user_message(_run_hook_process(environment))
    assert "stopped at an earlier session start before its install of 2.12.0 ended" in (
        message
    )
    assert _all_in_progress_records(tmp_path) == []


def should_stay_quiet_when_an_install_left_by_a_stopped_hook_finished(
    tmp_path: Path,
) -> None:
    _seed_sandbox(tmp_path, "2.12.0", None)
    in_progress_record = _config_directory(tmp_path) / IN_PROGRESS_RECORD_NAME
    in_progress_record.write_text("2.12.0", encoding="utf-8")
    environment = _hook_environment(
        tmp_path,
        remote=True,
        registry_version="2.12.0",
        registry_failure=False,
        config_dir_version=None,
    )
    completed = _run_hook_process(environment)
    assert completed.stdout == ""
    assert not in_progress_record.exists()


def should_tell_the_user_when_the_hook_stops_on_an_error(tmp_path: Path) -> None:
    environment = _stale_install_environment(tmp_path)
    config_file = tmp_path / "config-is-a-file"
    config_file.write_text("", encoding="utf-8")
    environment["CLAUDE_CONFIG_DIR"] = str(config_file)
    message = _user_message(_run_hook_process(environment))
    assert "the refresh hook stopped on FileExistsError" in message
    assert "npx -y claude-dev-env@latest" in message


def _refresh_hook_module() -> ModuleType:
    sys.path.insert(0, str(HOOK_SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location(
            "session_start_refresh_under_test", HOOK_SCRIPT
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(HOOK_SCRIPT.parent))
    return module


def should_render_every_refresh_outcome_with_a_command_to_run() -> None:
    hook = _refresh_hook_module()
    all_rendered = {
        outcome.name: hook.render_message(
            outcome,
            version="2.12.0",
            install_command="npx -y claude-dev-env@2.12.0",
            exit_code=1,
            signal_number=9,
            installed_version="2.9.0",
            error="OSError",
        )
        for outcome in hook.RefreshOutcome
    }
    assert len(all_rendered) == 9
    for outcome_name, message in all_rendered.items():
        assert message.startswith("claude-dev-env refresh: "), outcome_name
        assert "run `npx -y claude-dev-env@" in message, outcome_name
        assert "{" not in message, outcome_name
