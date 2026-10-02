#!/usr/bin/env python3
"""Name the Codex account a runner job uses, and keep each account's home ready.

Each Codex account signs in under its own Codex home in
``~/.codex-profiles/<name>``. The account roster names them in try order: the
``CODEX_ACCOUNT_PROFILES`` environment variable, comma-separated, else the saved
``account-launchers.json`` list under the profiles root. With neither,
``codex-1`` through ``codex-4`` are the roster. Jobs try them in that order::

    first account with more than 10% left              -> normal, that account
    none over 10%, the roomiest one over 1%            -> luna, stop at 1% left
    ... but an account with a 5-hour window needs 20% of it left for luna
    none over 1%, or no meter reads                    -> wait, name the first reset
    account not signed in, or its meter unread         -> skipped

Five commands::

    python codex_account_choice.py choose
    {"tier": "normal", "account": "codex-1", "codex_home": "C:/Users/me/.codex-profiles/codex-1",
     "percent_left": 62.0, "stop_below_percent": null, "reason": "codex-1 has 62% left",
     "accounts": [...]}

    python codex_account_choice.py check codex-2 --floor 1
    exit 0 while codex-2 has more than 1% left, exit 3 once it has not

    python codex_account_choice.py sync
    links the shared Codex setup (config, rules, skills, plugins, agents) into
    every roster account's home and leaves each sign-in and history its own

    python codex_account_choice.py setup
    asks for each account name, saves the roster, and writes one
    codex-<name>.cmd launcher per account; a dropped name's launcher moves aside

    python codex_account_choice.py install
    reruns the setup without asking: syncs every saved account's home and launcher
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from claude_account_profile import (
    move_launcher_aside,
    sync_profile,
    sync_report_payload,
    validate_profile_name,
    write_launcher,
)
from codex_account_meters import (
    CodexAccountMeters,
    CodexMeterUnreadError,
    read_codex_meters,
    resolve_codex_path,
)
from dev_env_scripts_constants.claude_account_constants import (
    ALL_LAUNCHER_DIRECTORY_RELATIVE_PARTS,
    JSON_LAUNCHER_KEY,
)
from dev_env_scripts_constants.codex_account_constants import (
    ALL_CODEX_ACCOUNT_NAMES,
    ALL_SHARED_CODEX_HOME_NAMES,
    CODEX_ACCOUNT_LAUNCHERS_FILE_NAME,
    CODEX_ACCOUNT_NAME_SEPARATOR,
    CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE,
    CODEX_AUTH_FILE_NAME,
    CODEX_LAUNCHER_FILE_NAME_TEMPLATE,
    CODEX_LAUNCHER_TEXT_TEMPLATE,
    CODEX_PROFILES_ROOT_DIRECTORY_NAME,
    CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE,
    COMMAND_INSTALL,
    COMMAND_SETUP,
    EXIT_CODE_NO_ROOM,
    EXIT_CODE_ROOM,
    INVALID_ACCOUNT_ROSTER_TEMPLATE,
    JSON_INSTALLED_KEY,
    JSON_RETIRED_KEY,
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    MAIN_CODEX_HOME_DIRECTORY_NAME,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    REASON_LUNA_TEMPLATE,
    REASON_NORMAL_TEMPLATE,
    REASON_WAIT_TEMPLATE,
    REASON_WAIT_UNREAD,
    ROSTER_JSON_INDENT,
    ROSTER_NOT_A_LIST_TEMPLATE,
    SETUP_NAMES_SEPARATOR,
    SETUP_NO_SAVED_NAMES_TEXT,
    SETUP_PROMPT_TEXT,
    SETUP_SAVED_NAMES_TEMPLATE,
    TEXT_ENCODING,
    TIER_LUNA,
    TIER_NORMAL,
    TIER_WAIT,
    UNKNOWN_ACCOUNT_TEMPLATE,
    UNKNOWN_RESET_TEXT,
    UNREAD_NOT_SIGNED_IN,
)

MeterReader = Callable[[Path], CodexAccountMeters]
LineReader = Callable[[str], str]
LineWriter = Callable[[str], None]


class CodexAccountNameError(ValueError):
    """An account name from the roster or the command line is invalid or unknown."""


@dataclass(frozen=True)
class AccountReading:
    """One account's meters, or why they could not be read."""

    name: str
    codex_home: Path
    meters: CodexAccountMeters | None
    unread_reason: str | None = None


@dataclass(frozen=True)
class CodexAccountDecision:
    """The tier and account a job runs on, and the plain-words reason."""

    tier: str
    reading: AccountReading | None
    stop_below_percent: float | None
    reason: str


def default_profiles_root() -> Path:
    """Locate the directory that holds one Codex home per account.

    Returns:
        The root the environment names, else ``~/.codex-profiles``.
    """
    named_root = os.environ.get(CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE)
    return (
        Path(named_root)
        if named_root
        else Path.home() / CODEX_PROFILES_ROOT_DIRECTORY_NAME
    )


def is_account_local_codex_entry(entry_name: str) -> bool:
    """Tell whether a Codex home entry belongs to one account only.

    ::

        "auth.json", "sessions", "history.jsonl", "state_5.sqlite" -> True
        "config.toml", "rules", "skills", "plugins"                -> False

    Args:
        entry_name: A top-level entry name in a Codex home.

    Returns:
        True for every entry outside the shared set.
    """
    return entry_name not in ALL_SHARED_CODEX_HOME_NAMES


def _validated_name(name: str, source: str) -> str:
    try:
        return validate_profile_name(name)
    except ValueError as error:
        raise CodexAccountNameError(
            INVALID_ACCOUNT_ROSTER_TEMPLATE.format(source=source, name=name, reason=error)
        ) from error


def _roster(all_raw_names: Sequence[str], source: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(_validated_name(each_name, source) for each_name in all_raw_names)
    )


def _environment_roster() -> tuple[str, ...]:
    raw_roster = os.environ.get(CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE, "")
    all_stripped = (
        each_part.strip() for each_part in raw_roster.split(CODEX_ACCOUNT_NAME_SEPARATOR)
    )
    all_raw_names = [each_name for each_name in all_stripped if each_name]
    return _roster(all_raw_names, CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE)


def _saved_roster_file_names(profiles_root: Path) -> tuple[str, ...]:
    """Read the roster saved under the profiles root, ignoring the environment.

    Args:
        profiles_root: The directory that holds every account's Codex home.

    Returns:
        The saved names in order, or nothing when no roster file exists.

    Raises:
        CodexAccountNameError: When the file holds anything but valid names.
    """
    roster_path = profiles_root / CODEX_ACCOUNT_LAUNCHERS_FILE_NAME
    if not roster_path.is_file():
        return ()
    try:
        document = json.loads(roster_path.read_text(encoding=TEXT_ENCODING))
    except json.JSONDecodeError:
        document = None
    if not isinstance(document, list) or not all(
        isinstance(each_name, str) for each_name in document
    ):
        raise CodexAccountNameError(ROSTER_NOT_A_LIST_TEMPLATE.format(source=roster_path))
    return _roster(document, str(roster_path))


def saved_codex_account_names(profiles_root: Path) -> tuple[str, ...]:
    """Name the account roster, in try order, without duplicates.

    ::

        CODEX_ACCOUNT_PROFILES="alpha, beta,alpha" -> ("alpha", "beta")
        unset, account-launchers.json ["gamma"]    -> ("gamma",)
        unset, no file                             -> ()

    Args:
        profiles_root: The directory that holds every account's Codex home.

    Returns:
        The environment's names when it names any, else the saved file's names.

    Raises:
        CodexAccountNameError: When the environment or the file names an invalid account.
    """
    return _environment_roster() or _saved_roster_file_names(profiles_root)


def codex_account_names(profiles_root: Path) -> tuple[str, ...]:
    """Name the accounts ``choose``, ``sync``, and ``check`` work on, in try order.

    Args:
        profiles_root: The directory that holds every account's Codex home.

    Returns:
        The account roster, else ``codex-1`` through ``codex-4``.
    """
    return saved_codex_account_names(profiles_root) or ALL_CODEX_ACCOUNT_NAMES


def save_codex_account_names(profiles_root: Path, all_names: Sequence[str]) -> None:
    """Write the account roster as a JSON list under the profiles root.

    Args:
        profiles_root: The directory that holds every account's Codex home.
        all_names: The account names in try order.
    """
    profiles_root.mkdir(parents=True, exist_ok=True)
    roster_text = json.dumps(list(all_names), indent=ROSTER_JSON_INDENT) + "\n"
    (profiles_root / CODEX_ACCOUNT_LAUNCHERS_FILE_NAME).write_bytes(
        roster_text.encode(TEXT_ENCODING)
    )


def _sync_account(
    *, main_home: Path, profiles_root: Path, name: str, now: datetime
) -> dict[str, object]:
    report = sync_profile(
        main_home=main_home,
        profile_home=profiles_root / name,
        now=now,
        is_local=is_account_local_codex_entry,
    )
    return sync_report_payload(report)


def _install_account(
    *, main_home: Path, profiles_root: Path, launcher_directory: Path, name: str, now: datetime
) -> dict[str, object]:
    sync_payload = _sync_account(
        main_home=main_home, profiles_root=profiles_root, name=name, now=now
    )
    launcher_path = write_launcher(
        launcher_directory=launcher_directory,
        profile_home=profiles_root / name,
        now=now,
        profile_name=name,
        launcher_file_name_template=CODEX_LAUNCHER_FILE_NAME_TEMPLATE,
        launcher_text_template=CODEX_LAUNCHER_TEXT_TEMPLATE,
    )
    return {**sync_payload, JSON_LAUNCHER_KEY: str(launcher_path)}


def install_codex_account_launchers(
    *,
    main_home: Path,
    profiles_root: Path,
    launcher_directory: Path,
    all_names: Sequence[str],
    now: datetime,
) -> dict[str, dict[str, object]]:
    """Link each account's home to the main Codex home and write its launcher, idempotently.

    Args:
        main_home: The Codex home that holds the shared setup.
        profiles_root: The directory that holds every account's Codex home.
        launcher_directory: The directory on PATH that holds the launchers.
        all_names: The account names to install.
        now: The run time that names anything moved aside.

    Returns:
        Per name, the entries linked, moved aside, and unlinked, and the launcher.
    """
    return {
        each_name: _install_account(
            main_home=main_home,
            profiles_root=profiles_root,
            launcher_directory=launcher_directory,
            name=each_name,
            now=now,
        )
        for each_name in all_names
    }


def _retire_codex_account_launchers(
    *, launcher_directory: Path, all_names: Sequence[str], now: datetime
) -> dict[str, str]:
    """Move each named account's launcher aside, leaving its Codex home alone.

    Args:
        launcher_directory: The directory on PATH that holds the launchers.
        all_names: The account names dropped from the roster.
        now: The run time that names each moved launcher.

    Returns:
        Per name with a launcher, the moved launcher's path.
    """
    all_retired: dict[str, str] = {}
    for each_name in all_names:
        launcher_path = launcher_directory / CODEX_LAUNCHER_FILE_NAME_TEMPLATE.format(
            profile_name=each_name
        )
        if launcher_path.is_file():
            all_retired[each_name] = str(move_launcher_aside(launcher_path, now))
    return all_retired


def _read_account_name(read_line: LineReader) -> str:
    try:
        return read_line(SETUP_PROMPT_TEXT).strip()
    except EOFError:
        return ""


def _prompt_codex_account_names(
    read_line: LineReader, write_line: LineWriter
) -> tuple[str, ...]:
    """Ask for account names until a blank line or the end of input.

    ::

        "alpha", "bad name", "alpha", "beta", "" -> ("alpha", "beta")

    Args:
        read_line: Shows the prompt and returns one typed line.
        write_line: Shows why a typed name was refused.

    Returns:
        The valid names in the order typed, without duplicates.
    """
    all_names: list[str] = []
    while entered_name := _read_account_name(read_line):
        try:
            all_names.append(validate_profile_name(entered_name))
        except ValueError as error:
            write_line(str(error))
    return tuple(dict.fromkeys(all_names))


def _ask_and_save_roster(
    profiles_root: Path, read_line: LineReader, write_line: LineWriter
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    all_saved = _saved_roster_file_names(profiles_root)
    write_line(
        SETUP_SAVED_NAMES_TEMPLATE.format(
            names=SETUP_NAMES_SEPARATOR.join(all_saved) or SETUP_NO_SAVED_NAMES_TEXT
        )
    )
    all_names = _prompt_codex_account_names(read_line, write_line)
    save_codex_account_names(profiles_root, all_names)
    all_dropped = tuple(
        each_name for each_name in all_saved if each_name not in all_names
    )
    return all_names, all_dropped


def update_codex_account_roster(
    *,
    profiles_root: Path,
    launcher_directory: Path,
    now: datetime,
    read_line: LineReader = input,
    write_line: LineWriter = print,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Ask for the account roster, save it, and move dropped launchers aside.

    Args:
        profiles_root: The directory that holds every account's Codex home.
        launcher_directory: The directory on PATH that holds the launchers.
        now: The run time that names each moved launcher.
        read_line: Shows the prompt and returns one typed line.
        write_line: Shows the saved roster and each refused name.

    Returns:
        The new roster, and per dropped name, the moved launcher's path.
    """
    all_names, all_dropped = _ask_and_save_roster(profiles_root, read_line, write_line)
    return all_names, _retire_codex_account_launchers(
        launcher_directory=launcher_directory, all_names=all_dropped, now=now
    )


def read_account(
    name: str, profiles_root: Path, read_meters: MeterReader
) -> AccountReading:
    """Read one account's meters from its Codex home.

    Args:
        name: The account name.
        profiles_root: The directory that holds every account's Codex home.
        read_meters: Reads the meters under one Codex home.

    Returns:
        The meters, or the reason they are unread.
    """
    codex_home = profiles_root / name
    if not (codex_home / CODEX_AUTH_FILE_NAME).is_file():
        return AccountReading(name, codex_home, None, UNREAD_NOT_SIGNED_IN)
    try:
        return AccountReading(name, codex_home, read_meters(codex_home))
    except CodexMeterUnreadError as error:
        return AccountReading(name, codex_home, None, str(error))


def _first_reset(
    all_read: Sequence[AccountReading],
) -> tuple[datetime, AccountReading] | None:
    all_resets = [
        (each_reset, each_reading)
        for each_reading in all_read
        if each_reading.meters is not None
        and (
            each_reset := each_reading.meters.resets_before_room(
                NORMAL_TIER_MINIMUM_PERCENT_LEFT
            )
        )
        is not None
    ]
    if not all_resets:
        return None
    return min(all_resets, key=lambda each_pair: each_pair[0])


def _wait_decision(all_read: Sequence[AccountReading]) -> CodexAccountDecision:
    if not all_read:
        return CodexAccountDecision(TIER_WAIT, None, None, REASON_WAIT_UNREAD)
    first_reset = _first_reset(all_read)
    if first_reset is None:
        reset_text, first_reading = UNKNOWN_RESET_TEXT, all_read[0]
    else:
        reset_text, first_reading = first_reset[0].isoformat(), first_reset[1]
    return CodexAccountDecision(
        TIER_WAIT,
        first_reading,
        None,
        REASON_WAIT_TEMPLATE.format(account=first_reading.name, reset=reset_text),
    )


def _percent_left(reading: AccountReading) -> float:
    return reading.meters.percent_left if reading.meters is not None else 0.0


def _normal_decision(all_read: Sequence[AccountReading]) -> CodexAccountDecision | None:
    for each_reading in all_read:
        percent_left = _percent_left(each_reading)
        if percent_left > NORMAL_TIER_MINIMUM_PERCENT_LEFT:
            return CodexAccountDecision(
                TIER_NORMAL,
                each_reading,
                None,
                REASON_NORMAL_TEMPLATE.format(
                    account=each_reading.name, percent_left=percent_left
                ),
            )
    return None


def _can_run_luna(reading: AccountReading) -> bool:
    if reading.meters is None or reading.meters.percent_left <= LUNA_TIER_STOP_PERCENT_LEFT:
        return False
    short_window_left = reading.meters.short_window_percent_left
    return (
        short_window_left is None
        or short_window_left >= LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT
    )


def _luna_decision(all_read: Sequence[AccountReading]) -> CodexAccountDecision | None:
    all_candidates = [each_reading for each_reading in all_read if _can_run_luna(each_reading)]
    if not all_candidates:
        return None
    roomiest = max(all_candidates, key=_percent_left)
    return CodexAccountDecision(
        TIER_LUNA,
        roomiest,
        LUNA_TIER_STOP_PERCENT_LEFT,
        REASON_LUNA_TEMPLATE.format(
            bar=NORMAL_TIER_MINIMUM_PERCENT_LEFT,
            account=roomiest.name,
            percent_left=_percent_left(roomiest),
            stop=LUNA_TIER_STOP_PERCENT_LEFT,
        ),
    )


def choose_codex_account(all_readings: Sequence[AccountReading]) -> CodexAccountDecision:
    """Pick the tier and account a job runs on.

    ::

        codex-1 8%, codex-2 40%          -> normal on codex-2
        codex-1 8%, codex-2 3%, others 0 -> luna on codex-1, stop at 1%
        codex-1 week 8%, 5-hour 15% left -> no luna on codex-1, 5-hour under 20%
        every account 1% or less         -> wait, naming the account that resets first
        codex-1 unread, codex-2 40%      -> normal on codex-2

    Args:
        all_readings: Every account's reading, in try order.

    Returns:
        The tier, the account, where a Luna run stops, and the reason.
    """
    all_read = [
        each_reading for each_reading in all_readings if each_reading.meters is not None
    ]
    return (
        _normal_decision(all_read)
        or _luna_decision(all_read)
        or _wait_decision(all_read)
    )


def _iso_or_none(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def reading_payload(reading: AccountReading) -> dict[str, object]:
    """Shape one account's reading as the JSON object a report prints.

    Args:
        reading: One account's reading.

    Returns:
        The name, percent left, each window, and any unread reason.
    """
    if reading.meters is None:
        return {
            "name": reading.name,
            "percent_left": None,
            "unread": reading.unread_reason,
        }
    return {
        "name": reading.name,
        "percent_left": reading.meters.percent_left,
        "windows": [
            {
                "minutes": each_window.duration_minutes,
                "used_percent": each_window.used_percent,
                "resets_at": _iso_or_none(each_window.resets_at),
            }
            for each_window in reading.meters.all_windows
        ],
    }


def decision_payload(
    decision: CodexAccountDecision, all_readings: Sequence[AccountReading]
) -> dict[str, object]:
    """Shape a decision as the JSON object the runner job reads.

    Args:
        decision: The chosen tier and account.
        all_readings: Every account's reading, for the report.

    Returns:
        The tier, account, Codex home, room, stop point, reason, and all readings.
    """
    is_runnable = decision.tier != TIER_WAIT and decision.reading is not None
    chosen = decision.reading if is_runnable else None
    return {
        "tier": decision.tier,
        "account": chosen.name if chosen else None,
        "codex_home": str(chosen.codex_home) if chosen else None,
        "percent_left": chosen.meters.percent_left
        if chosen and chosen.meters
        else None,
        "stop_below_percent": decision.stop_below_percent,
        "reason": decision.reason,
        "accounts": [reading_payload(each_reading) for each_reading in all_readings],
    }


def _meter_reader(codex_path_argument: Path | None) -> MeterReader:
    codex_path = resolve_codex_path(codex_path_argument)
    return lambda codex_home: read_codex_meters(codex_path, codex_home)


def _run_choose(arguments: argparse.Namespace) -> int:
    read_meters = _meter_reader(arguments.codex_path)
    all_readings = [
        read_account(each_name, arguments.profiles_root, read_meters)
        for each_name in codex_account_names(arguments.profiles_root)
    ]
    print(
        json.dumps(decision_payload(choose_codex_account(all_readings), all_readings))
    )
    return 0


def _require_known_account(name: str, profiles_root: Path) -> None:
    all_known = codex_account_names(profiles_root)
    if name not in all_known:
        raise CodexAccountNameError(
            UNKNOWN_ACCOUNT_TEMPLATE.format(
                name=name, known=SETUP_NAMES_SEPARATOR.join(all_known)
            )
        )


def _run_check(arguments: argparse.Namespace) -> int:
    _require_known_account(arguments.account, arguments.profiles_root)
    reading = read_account(
        arguments.account, arguments.profiles_root, _meter_reader(arguments.codex_path)
    )
    print(json.dumps(reading_payload(reading)))
    if reading.meters is not None and reading.meters.percent_left > arguments.floor:
        return EXIT_CODE_ROOM
    return EXIT_CODE_NO_ROOM


def _run_sync(arguments: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    all_reports = {
        each_name: _sync_account(
            main_home=arguments.main_home,
            profiles_root=arguments.profiles_root,
            name=each_name,
            now=now,
        )
        for each_name in codex_account_names(arguments.profiles_root)
    }
    print(json.dumps(all_reports))
    return 0


def _run_install(arguments: argparse.Namespace) -> int:
    all_reports = install_codex_account_launchers(
        main_home=arguments.main_home,
        profiles_root=arguments.profiles_root,
        launcher_directory=arguments.launcher_directory,
        all_names=saved_codex_account_names(arguments.profiles_root),
        now=datetime.now(timezone.utc),
    )
    print(json.dumps(all_reports))
    return 0


def _run_setup(arguments: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    all_names, all_retired = update_codex_account_roster(
        profiles_root=arguments.profiles_root,
        launcher_directory=arguments.launcher_directory,
        now=now,
    )
    all_installed = install_codex_account_launchers(
        main_home=arguments.main_home,
        profiles_root=arguments.profiles_root,
        launcher_directory=arguments.launcher_directory,
        all_names=all_names,
        now=now,
    )
    print(json.dumps({JSON_INSTALLED_KEY: all_installed, JSON_RETIRED_KEY: all_retired}))
    return 0


def _add_main_home_argument(command_parser: argparse.ArgumentParser) -> None:
    command_parser.add_argument(
        "--main-home", type=Path, default=Path.home() / MAIN_CODEX_HOME_DIRECTORY_NAME
    )


def _add_launcher_commands(
    all_commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    all_launcher_commands = ((COMMAND_SETUP, _run_setup), (COMMAND_INSTALL, _run_install))
    for each_command, each_run in all_launcher_commands:
        command_parser = all_commands.add_parser(each_command)
        _add_main_home_argument(command_parser)
        command_parser.add_argument(
            "--launcher-directory",
            type=Path,
            default=Path.home().joinpath(*ALL_LAUNCHER_DIRECTORY_RELATIVE_PARTS),
        )
        command_parser.set_defaults(run=each_run)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Name the Codex account a runner job uses."
    )
    parser.add_argument("--profiles-root", type=Path, default=default_profiles_root())
    parser.add_argument("--codex-path", type=Path, default=None)
    all_commands = parser.add_subparsers(dest="command", required=True)
    all_commands.add_parser("choose").set_defaults(run=_run_choose)
    check_parser = all_commands.add_parser("check")
    check_parser.add_argument("account")
    check_parser.add_argument(
        "--floor", type=float, default=LUNA_TIER_STOP_PERCENT_LEFT
    )
    check_parser.set_defaults(run=_run_check)
    sync_parser = all_commands.add_parser("sync")
    _add_main_home_argument(sync_parser)
    sync_parser.set_defaults(run=_run_sync)
    _add_launcher_commands(all_commands)
    return parser


def main(all_command_arguments: list[str]) -> int:
    """Run one command and print its JSON report.

    Args:
        all_command_arguments: Command-line arguments after the program name.

    Returns:
        Zero for choose, sync, setup, and install; for check, zero with room and
        three without. An invalid or unknown account name exits through the
        parser with two.
    """
    parser = _build_argument_parser()
    arguments = parser.parse_args(all_command_arguments)
    try:
        return arguments.run(arguments)
    except CodexAccountNameError as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
