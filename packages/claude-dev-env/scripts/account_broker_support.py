"""Choose and run Claude or Codex jobs through one account roster."""

from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

import codex_account_choice
import codex_account_meters
from claude_account_profile import default_profile_home, validate_profile_name
from claude_chain_usage import WeeklyUtilizationProbeError, probe_account_meters
from dev_env_scripts_constants.account_broker_constants import (
    ALL_BATCH_FILE_EXTENSIONS,
    BROKER_STATE_DIRECTORY_NAME,
    BROKER_STATE_FILE_NAME,
    BROKER_STATE_LOCK_SUFFIX,
    BROKER_STATE_TEMP_SUFFIX,
    Account,
    BrokerConfigurationError,
    CMD_SHELL_METACHARACTERS,
    Decision,
    JobOutcome,
    Meters,
    Product,
    ProductAdapter,
    Reading,
    Report,
    REPORT_INDENT_SPACES,
    SubprocessRunner,
    codex_usage_limit_signatures,
    parse_utc_time,
    utc_time_text,
)
from dev_env_scripts_constants.claude_account_constants import (
    CREDENTIALS_FILE_NAME,
    EXTRA_PROFILES_FILE_NAME,
    FULL_PERCENT,
    MAIN_CLAUDE_HOME_DIRECTORY_NAME,
)
from dev_env_scripts_constants.claude_chain_constants import ALL_USAGE_LIMIT_SIGNATURES
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_ACCOUNT_LAUNCHERS_FILE_NAME,
    CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE,
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    WEEKLY_WINDOW_MINUTES,
)
from dev_env_scripts_constants.shared_tree_constants import CLAUDE_CONFIG_DIR_ENV_VAR


def _read_list(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BrokerConfigurationError(f"cannot read account list {path}: {error}") from error


def _chain_entry(raw_entry: object, main_home: Path, chain_path: Path) -> Account:
    if not isinstance(raw_entry, dict):
        raise BrokerConfigurationError(f"invalid account list {chain_path}")
    command = raw_entry.get("command")
    credential = raw_entry.get("credentials_path")
    extra_args = raw_entry.get("extra_args", [])
    if not isinstance(command, str) or not command:
        raise BrokerConfigurationError(f"invalid account list {chain_path}")
    if credential is not None and (not isinstance(credential, str) or not credential):
        raise BrokerConfigurationError(f"invalid account list {chain_path}")
    if not isinstance(extra_args, list) or any(not isinstance(each_arg, str) for each_arg in extra_args):
        raise BrokerConfigurationError(f"invalid account list {chain_path}")
    home = Path(credential).expanduser().parent.resolve() if credential else main_home
    return Account(Product.CLAUDE, command, home, command=command)


def _chain_entries(chain_path: Path, main_home: Path) -> tuple[Account, ...]:
    if not chain_path.exists():
        return ()
    document = _read_list(chain_path)
    all_entries = document.get("chain") if isinstance(document, dict) else None
    if not isinstance(all_entries, list) or not all_entries:
        raise BrokerConfigurationError(f"invalid account list {chain_path}")
    return tuple(_chain_entry(each_entry, main_home, chain_path) for each_entry in all_entries)


def _extra_homes(main_home: Path) -> tuple[Path, ...]:
    extras_path = main_home / EXTRA_PROFILES_FILE_NAME
    if not extras_path.exists():
        return (default_profile_home(),)
    all_names = _read_list(extras_path)
    if not isinstance(all_names, list) or not all_names or any(not isinstance(each_name, str) for each_name in all_names):
        raise BrokerConfigurationError(f"invalid account list {extras_path}")
    if len({each_name.casefold() for each_name in all_names}) != len(all_names):
        raise BrokerConfigurationError(f"duplicate account in {extras_path}")
    try:
        return tuple(default_profile_home(validate_profile_name(each_name)) for each_name in all_names)
    except ValueError as error:
        raise BrokerConfigurationError(f"invalid account list {extras_path}: {error}") from error


def _append_claude_account(
    all_accounts: list[Account], all_seen: set[str], account: Account, main_home: Path
) -> None:
    key = str(account.home).casefold()
    if key == str(main_home).casefold():
        all_accounts[0] = Account(Product.CLAUDE, "main", main_home, True, account.command)
    elif key not in all_seen:
        all_accounts.append(account)
        all_seen.add(key)


def load_claude_accounts() -> tuple[Account, ...]:
    """Read the Claude account roster.

    Returns:
        Main and additional accounts in configured order.

    Raises:
        BrokerConfigurationError: An account list is unreadable.
    """
    main_home = (Path.home() / MAIN_CLAUDE_HOME_DIRECTORY_NAME).resolve()
    all_accounts = [Account(Product.CLAUDE, "main", main_home, True, "claude")]
    all_seen = {str(main_home).casefold()}
    for each_entry in _chain_entries(main_home / "claude-chain.json", main_home):
        _append_claude_account(all_accounts, all_seen, each_entry, main_home)
    for each_home in _extra_homes(main_home):
        home = each_home.resolve()
        _append_claude_account(all_accounts, all_seen, Account(Product.CLAUDE, home.name, home, command=home.name), main_home)
    return tuple(all_accounts)


def load_codex_accounts() -> tuple[Account, ...]:
    """Read the Codex account roster.

    Returns:
        Configured accounts, or an empty tuple when none are configured.

    Raises:
        BrokerConfigurationError: The configured roster is unreadable.
    """
    profiles_root = codex_account_choice.default_profiles_root().resolve()
    roster_path = profiles_root / CODEX_ACCOUNT_LAUNCHERS_FILE_NAME
    configured = bool(os.environ.get(CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE, "").strip())
    if not configured and not roster_path.exists():
        return ()
    if not configured and _read_list(roster_path) == []:
        return ()
    try:
        names = codex_account_choice.codex_account_names(profiles_root)
    except (OSError, ValueError) as error:
        raise BrokerConfigurationError(f"cannot read account list {roster_path}: {error}") from error
    return tuple(Account(Product.CODEX, name, (profiles_root / name).resolve()) for name in names)


def read_claude_meters(account: Account) -> Meters | None:
    """Probe one Claude account.

    Args:
        account: Account whose meter is read.

    Returns:
        Its meters, or None when the probe fails.
    """
    try:
        usage = probe_account_meters(account.home / CREDENTIALS_FILE_NAME)
    except (WeeklyUtilizationProbeError, OSError):
        return None
    return Meters(
        FULL_PERCENT - usage.session_utilization if usage.session_utilization is not None else None,
        usage.session_resets_at,
        FULL_PERCENT - usage.weekly_utilization if usage.weekly_utilization is not None else None,
        usage.weekly_resets_at,
    )


def read_codex_account_meters(account: Account) -> Meters | None:
    """Probe one Codex account.

    Args:
        account: Account whose meter is read.

    Returns:
        Its meters, or None when the probe fails.
    """
    try:
        codex_path = codex_account_meters.resolve_codex_path(None)
        usage = codex_account_meters.read_codex_meters(codex_path, account.home)
    except (codex_account_meters.CodexMeterUnreadError, OSError):
        return None
    weekly = [window for window in usage.all_windows if window.duration_minutes is None or window.duration_minutes >= WEEKLY_WINDOW_MINUTES]
    short = [window for window in usage.all_windows if window.duration_minutes is not None and window.duration_minutes < WEEKLY_WINDOW_MINUTES]
    weekly_window = max(weekly, key=lambda window: window.used_percent) if weekly else None
    short_window = max(short, key=lambda window: window.used_percent) if short else None
    return Meters(
        usage.short_window_percent_left,
        short_window.resets_at if short_window else None,
        FULL_PERCENT - weekly_window.used_percent if weekly_window else None,
        weekly_window.resets_at if weekly_window else None,
    )


all_product_adapters = {
    Product.CLAUDE: ProductAdapter(load_claude_accounts, read_claude_meters, CLAUDE_CONFIG_DIR_ENV_VAR, ALL_USAGE_LIMIT_SIGNATURES, True),
    Product.CODEX: ProductAdapter(load_codex_accounts, read_codex_account_meters, CODEX_HOME_ENVIRONMENT_VARIABLE, codex_usage_limit_signatures(), False),
}


def broker_state_path() -> Path:
    return Path.home() / MAIN_CLAUDE_HOME_DIRECTORY_NAME / BROKER_STATE_DIRECTORY_NAME / BROKER_STATE_FILE_NAME


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"meters": {}, "spent": {}, "affinity": {}}
    try:
        parsed_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"meters": {}, "spent": {}, "affinity": {}}
    if not isinstance(parsed_state, dict):
        return {"meters": {}, "spent": {}, "affinity": {}}
    return {key: parsed_state.get(key) if isinstance(parsed_state.get(key), dict) else {} for key in ("meters", "spent", "affinity")}


def _acquire_windows_lock(lock_descriptor: int, locking: Callable[[int, int, int], None], lock_mode: int) -> None:
    """Lock the first byte of *lock_descriptor*, retrying while another process holds it.

    ``msvcrt.locking`` with ``LK_LOCK`` gives up after ten one-second attempts and
    raises ``OSError`` with ``EDEADLOCK``. That error means the lock is still busy, so
    the call repeats until it succeeds, matching ``fcntl.flock`` on POSIX. Any other
    ``OSError`` propagates.

    Args:
        lock_descriptor: Open descriptor of the lock file.
        locking: The ``msvcrt.locking`` function.
        lock_mode: The blocking lock mode passed to ``locking``.
    """
    is_locked = False
    while not is_locked:
        is_locked = _attempt_windows_lock(lock_descriptor, locking, lock_mode)


def _attempt_windows_lock(lock_descriptor: int, locking: Callable[[int, int, int], None], lock_mode: int) -> bool:
    os.lseek(lock_descriptor, 0, os.SEEK_SET)
    try:
        locking(lock_descriptor, lock_mode, 1)
    except OSError as error:
        if error.errno != errno.EDEADLOCK:
            raise
        return False
    return True


if sys.platform == "win32":

    def _acquire_state_lock(lock_descriptor: int) -> None:
        _acquire_windows_lock(lock_descriptor, msvcrt.locking, msvcrt.LK_LOCK)

    def _release_state_lock(lock_descriptor: int) -> None:
        os.lseek(lock_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(lock_descriptor, msvcrt.LK_UNLCK, 1)

else:

    def _acquire_state_lock(lock_descriptor: int) -> None:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)

    def _release_state_lock(lock_descriptor: int) -> None:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)


@contextmanager
def _state_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive operating-system lock on the state file's sibling lock file."""
    lock_descriptor = os.open(path.with_name(path.name + BROKER_STATE_LOCK_SUFFIX), os.O_CREAT | os.O_RDWR)
    try:
        _acquire_state_lock(lock_descriptor)
        try:
            yield
        finally:
            _release_state_lock(lock_descriptor)
    finally:
        os.close(lock_descriptor)


def _read_at(entry: object) -> float:
    if not isinstance(entry, dict):
        return float("-inf")
    read_at = entry.get("read_at")
    return float(read_at) if isinstance(read_at, (int, float)) else float("-inf")


def _merged_state(all_saved_state: dict[str, object], all_unsaved_state: dict[str, object]) -> dict[str, object]:
    """Combine two state documents so each writer keeps the other writer's entries.

    A spent mark keeps its latest reset, a meter entry keeps its newest read,
    and the unsaved session bindings take their keys.
    """
    all_meters = dict(all_saved_state["meters"])
    for each_key, each_entry in all_unsaved_state["meters"].items():
        if _read_at(each_entry) >= _read_at(all_meters.get(each_key)):
            all_meters[each_key] = each_entry
    all_spent = dict(all_saved_state["spent"])
    for each_key, each_reset in all_unsaved_state["spent"].items():
        saved_reset = all_spent.get(each_key)
        if not isinstance(saved_reset, (int, float)) or (isinstance(each_reset, (int, float)) and each_reset > saved_reset):
            all_spent[each_key] = each_reset
    return {"meters": all_meters, "spent": all_spent, "affinity": {**all_saved_state["affinity"], **all_unsaved_state["affinity"]}}


def _save_state(path: Path, all_state: dict[str, object]) -> None:
    """Merge the caller's state into the saved file under a lock, then refresh the caller's copy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _state_lock(path):
        all_state.update(_merged_state(_load_state(path), all_state))
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix="state-", suffix=BROKER_STATE_TEMP_SUFFIX, delete=False, newline="\n") as stream:
                temporary_name = stream.name
                json.dump(all_state, stream, indent=REPORT_INDENT_SPACES, sort_keys=True)
                stream.write("\n")
            os.replace(temporary_name, path)
        finally:
            if temporary_name is not None and os.path.exists(temporary_name):
                os.unlink(temporary_name)


def _state_key(account: Account) -> str:
    return f"{account.product.value}:{account.name}:{account.home}"


def _meter_payload(meters: Meters | None) -> dict[str, object] | None:
    if meters is None:
        return None
    return {
        "session_percent_left": meters.session_percent_left,
        "session_resets_at": utc_time_text(meters.session_resets_at),
        "weekly_percent_left": meters.weekly_percent_left,
        "weekly_resets_at": utc_time_text(meters.weekly_resets_at),
    }


def _meters_from_payload(raw_meters: object) -> Meters | None:
    if not isinstance(raw_meters, dict):
        return None
    all_percentages = (raw_meters.get("session_percent_left"), raw_meters.get("weekly_percent_left"))
    if any(each_percent is not None and not isinstance(each_percent, (int, float)) for each_percent in all_percentages):
        return None
    return Meters(all_percentages[0], parse_utc_time(raw_meters.get("session_resets_at")), all_percentages[1], parse_utc_time(raw_meters.get("weekly_resets_at")))


def _read_one_account(account: Account, adapter: ProductAdapter, all_cache: dict[str, object], now: datetime) -> tuple[Reading, bool]:
    key = _state_key(account)
    cached = all_cache.get(key)
    if isinstance(cached, dict) and isinstance(cached.get("read_at"), (int, float)) and 0 <= now.timestamp() - cached["read_at"] < 60:
        return Reading(account, _meters_from_payload(cached.get("meters"))), False
    try:
        meters = adapter.read_meters(account)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        meters = None
    all_cache[key] = {"read_at": now.timestamp(), "meters": _meter_payload(meters)}
    return Reading(account, meters), True


def read_accounts(product: Product, adapter: ProductAdapter | None = None, *, all_state: dict[str, object] | None = None, now: datetime | None = None) -> tuple[Reading, ...]:
    """Read account meters with a 60-second cache.

    Args:
        product: Product whose accounts are read.
        adapter: Injected account and meter readers.
        all_state: Mutable broker state document.
        now: Clock instant used for cache age.

    Returns:
        Account readings in roster order.
    """
    active = adapter or all_product_adapters[product]
    current = now or datetime.now(timezone.utc)
    all_cache = all_state.get("meters", {}) if all_state is not None else {}
    all_readings: list[Reading] = []
    is_updated = False
    for each_account in active.load_accounts():
        reading, did_read = _read_one_account(each_account, active, all_cache, current)
        all_readings.append(reading)
        is_updated = is_updated or did_read
    if is_updated and all_state is not None:
        _save_state(broker_state_path(), all_state)
    return tuple(all_readings)


def _session_id_from_json(value: str) -> str | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    return session_id if isinstance(session_id, str) and session_id else None


def extract_session_id_from_stdout(stdout: str) -> str | None:
    """Find a session id in JSON or newline-delimited JSON.

    Args:
        stdout: Captured command output.

    Returns:
        Session id, if present.
    """
    return _session_id_from_json(stdout.strip()) or next(
        (found for line in stdout.splitlines() if (found := _session_id_from_json(line.strip())) is not None),
        None,
    )


def _resume_id(all_argv: Sequence[str]) -> str | None:
    for each_index, each_argument in enumerate(all_argv):
        if each_argument == "--resume" and each_index + 1 < len(all_argv):
            candidate = all_argv[each_index + 1]
            return candidate if candidate and not candidate.startswith("-") else None
    return None


def _resolve_command(all_argv: Sequence[str]) -> list[str]:
    command_name, *all_arguments = all_argv
    resolved_command = shutil.which(command_name)
    if resolved_command is None and not os.path.dirname(command_name):
        raise FileNotFoundError(errno.ENOENT, "command not found on PATH", command_name)
    launched_command = resolved_command or command_name
    _refuse_batch_file_shell_metacharacters(launched_command, all_arguments)
    return [launched_command, *all_arguments]


def _refuse_batch_file_shell_metacharacters(launched_command: str, all_arguments: Sequence[str]) -> None:
    if os.path.splitext(launched_command)[1].casefold() not in ALL_BATCH_FILE_EXTENSIONS:
        return
    shell_parsed_argument = next(
        (
            each_argument
            for each_argument in all_arguments
            if any(each_character in CMD_SHELL_METACHARACTERS for each_character in each_argument)
        ),
        None,
    )
    if shell_parsed_argument is None:
        return
    raise OSError(
        errno.EINVAL,
        f"cmd.exe would parse the batch file argument {shell_parsed_argument!r}; send that text on stdin",
        launched_command,
    )


def _run_captured_subprocess(all_argv: Sequence[str], **options: object) -> subprocess.CompletedProcess[str]:
    encoding = str(options.get("encoding") or "utf-8")
    errors = str(options.get("errors") or "replace")
    stdin_bytes = options.get("input")
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        completion = subprocess.run(
            _resolve_command(all_argv),
            input=stdin_bytes,
            stdout=stdout_file,
            stderr=stderr_file,
            env=options.get("env"),
            cwd=options.get("cwd"),
            timeout=options.get("timeout"),
            check=False,
        )
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().decode(encoding, errors).replace("\r\n", "\n").replace("\r", "\n")
        stderr = stderr_file.read().decode(encoding, errors).replace("\r\n", "\n").replace("\r", "\n")
    return subprocess.CompletedProcess(list(all_argv), completion.returncode, stdout, stderr)


subprocess_runner: SubprocessRunner = _run_captured_subprocess
_subprocess_runner_lock = threading.Lock()


@contextmanager
def override_subprocess_runner(runner: SubprocessRunner) -> Iterator[SubprocessRunner]:
    """Replace the captured subprocess runner within a context.

    Args:
        runner: Replacement runner.

    Yields:
        Runner that was active before replacement.
    """
    global subprocess_runner
    with _subprocess_runner_lock:
        previous = subprocess_runner
        subprocess_runner = runner
        try:
            yield previous
        finally:
            subprocess_runner = previous
