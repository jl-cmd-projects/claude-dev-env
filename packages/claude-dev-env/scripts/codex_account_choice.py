#!/usr/bin/env python3
"""Keep each Codex account's home and launcher ready.

Each Codex account signs in under its own Codex home in
``~/.codex-profiles/<name>``. The account roster names them in try order: the
``CODEX_ACCOUNT_PROFILES`` environment variable, comma-separated, else the saved
``account-launchers.json`` list under the profiles root. With neither,
``codex-1`` through ``codex-4`` are the roster.

Three commands::

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
from datetime import datetime, timezone
from pathlib import Path

from claude_account_profile import (
    launcher_path,
    move_launcher_aside,
    sync_profile,
    sync_report_payload,
    validate_profile_name,
    write_launcher,
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
    CODEX_LAUNCHER_PROGRAM,
    CODEX_PROFILES_ROOT_DIRECTORY_NAME,
    CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE,
    COMMAND_INSTALL,
    COMMAND_SETUP,
    INVALID_ACCOUNT_ROSTER_TEMPLATE,
    JSON_INSTALLED_KEY,
    JSON_RETIRED_KEY,
    MAIN_CODEX_HOME_DIRECTORY_NAME,
    ROSTER_JSON_INDENT,
    ROSTER_NOT_A_LIST_TEMPLATE,
    SETUP_NAMES_SEPARATOR,
    SETUP_NO_SAVED_NAMES_TEXT,
    SETUP_PROMPT_TEXT,
    SETUP_SAVED_NAMES_TEMPLATE,
    TEXT_ENCODING,
)

LineReader = Callable[[str], str]
LineWriter = Callable[[str], None]


class CodexAccountNameError(ValueError):
    """An account name from the roster is invalid or unknown."""


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
    """Name the accounts the broker and setup commands use, in try order.

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
        launcher_program=CODEX_LAUNCHER_PROGRAM,
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
        retired_path = launcher_path(launcher_directory, each_name, CODEX_LAUNCHER_PROGRAM)
        if retired_path.is_file():
            all_retired[each_name] = str(move_launcher_aside(retired_path, now))
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


def _ask_roster(
    profiles_root: Path, read_line: LineReader, write_line: LineWriter
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    all_saved = _saved_roster_file_names(profiles_root)
    write_line(
        SETUP_SAVED_NAMES_TEMPLATE.format(
            names=SETUP_NAMES_SEPARATOR.join(all_saved) or SETUP_NO_SAVED_NAMES_TEXT
        )
    )
    all_names = _prompt_codex_account_names(read_line, write_line)
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
    all_names, all_dropped = _ask_roster(profiles_root, read_line, write_line)
    all_retired = _retire_codex_account_launchers(
        launcher_directory=launcher_directory, all_names=all_dropped, now=now
    )
    save_codex_account_names(profiles_root, all_names)
    return all_names, all_retired



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
        description="Keep Codex account homes and launchers ready."
    )
    parser.add_argument("--profiles-root", type=Path, default=default_profiles_root())
    all_commands = parser.add_subparsers(dest="command", required=True)
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
        Zero for sync, setup, and install. An invalid account name exits
        through the parser with two.
    """
    parser = _build_argument_parser()
    arguments = parser.parse_args(all_command_arguments)
    try:
        return arguments.run(arguments)
    except CodexAccountNameError as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
