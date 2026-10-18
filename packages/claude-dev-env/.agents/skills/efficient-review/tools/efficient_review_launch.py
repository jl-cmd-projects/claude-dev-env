"""Prepare Claude accounts, launchers, and one review command."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PureWindowsPath

from tools import review_profile
from tools.config import efficient_review_constants as c
from tools.config import review_profile_constants as profile_constants
from tools.config import review_run_constants as run_constants
from tools.config.efficient_review_settings import load_settings, string_list
from tools.efficient_review_request import ReviewRequest, ReviewRequestRunFatal
from tools.review_command import review_command, review_system_prompt, write_system_prompt
from tools.review_rules import review_rules_text


def discover_accounts(home: Path) -> tuple[list[str], str]:
    """Return the offered launcher accounts and their source.

    Args:
        home: The user home that may contain Claude launchers.

    Returns:
        The offered account names and either the launcher or roster source.
    """
    all_settings = load_settings()
    all_offered = _launcher_accounts(home, all_settings)
    if all_offered:
        return all_offered, c.ACCOUNT_SOURCE_LAUNCHERS
    return list(string_list(all_settings, "known_accounts")), c.ACCOUNT_SOURCE_ROSTER


def _launcher_accounts(home: Path, all_settings: dict[str, object]) -> list[str]:
    directory_parts = string_list(all_settings, "launcher_directory_parts")
    prefix = str(all_settings["launcher_prefix"])
    suffix = str(all_settings["launcher_suffix"])
    launcher_directory = home.joinpath(*directory_parts)
    if not launcher_directory.is_dir():
        return []
    all_accounts = sorted(
        each_path.name.removeprefix(prefix).removesuffix(suffix)
        for each_path in launcher_directory.glob(f"{prefix}*{suffix}")
    )
    excluded = set(string_list(all_settings, "excluded_accounts"))
    return [each for each in all_accounts if each not in excluded]


def broker_account(
    run: Callable[..., subprocess.CompletedProcess[str]], home: Path
) -> tuple[str, str]:
    """Return the account broker's selected Claude account and reason.

    Args:
        run: The process runner, usually subprocess.run.
        home: The user home that holds the broker script.

    Returns:
        The selected account name, or its launcher path, and broker reason.

    Raises:
        RuntimeError: The broker failed, all accounts wait, or its pick is invalid.
    """
    return _parse_broker_decision(_run_broker(run, home))


def _run_broker(
    run: Callable[..., subprocess.CompletedProcess[str]], home: Path
) -> subprocess.CompletedProcess[str]:
    all_settings = load_settings()
    return run(
        [
            sys.executable,
            str(home.joinpath(*string_list(all_settings, "broker_relative_parts"))),
            "choose",
            "--product",
            c.HARNESS_CLAUDE,
        ],
        capture_output=True,
        text=True,
        encoding=c.TEXT_ENCODING,
        check=False,
    )


def _parse_broker_decision(
    completed: subprocess.CompletedProcess[str],
) -> tuple[str, str]:
    if completed.returncode not in (0, c.BROKER_WAIT_EXIT_CODE):
        raise RuntimeError(
            f"account broker exited {completed.returncode}: {completed.stderr}"
        )
    decision = json.loads(completed.stdout)["decision"]
    if completed.returncode == c.BROKER_WAIT_EXIT_CODE:
        raise RuntimeError(f"every account waits: {decision.get('reason')}")
    account = str(decision.get("account") or "")
    if not c.ACCOUNT_NAME_PATTERN.fullmatch(_account_name(account)):
        raise RuntimeError(
            f"the broker picked {account!r}, which is not an account name"
        )
    return account, str(decision.get("reason") or "")


def _account_name(picked: str) -> str:
    all_settings = load_settings()
    prefix = str(all_settings["launcher_prefix"])
    suffix = str(all_settings["launcher_suffix"])
    launcher_name = PureWindowsPath(picked).name
    is_launcher = launcher_name.startswith(prefix) and launcher_name.endswith(suffix)
    if is_launcher and launcher_name != picked:
        return launcher_name[len(prefix) : -len(suffix)]
    return picked


def launcher_path(home: Path, account: str) -> Path:
    """Return the account launcher.

    Args:
        home: The user home that contains the launcher directory.
        account: The selected account name, or a launcher path.

    Returns:
        The existing launcher path.

    Raises:
        FileNotFoundError: No launcher exists for the account.
    """
    path = _launcher_candidate(home, account)
    if not path.is_file():
        raise FileNotFoundError(f"no launcher at {path}")
    return path


def _launcher_candidate(home: Path, account: str) -> Path:
    if _account_name(account) != account:
        return Path(account)
    all_settings = load_settings()
    prefix = str(all_settings["launcher_prefix"])
    suffix = str(all_settings["launcher_suffix"])
    return (
        home.joinpath(*string_list(all_settings, "launcher_directory_parts"))
        / f"{prefix}{account}{suffix}"
    )


def launcher_home(launcher: Path) -> dict[str, str]:
    """Return the CLAUDE_CONFIG_DIR set by a launcher, if present.

    Args:
        launcher: The account launcher file to inspect.

    Returns:
        The environment entry, or an empty mapping if the launcher omits it.
    """
    pattern = str(load_settings()["launcher_home_pattern"])
    match = re.search(pattern, launcher.read_text(encoding=c.TEXT_ENCODING, errors="replace"))
    if match is None:
        return {}
    return {c.CLAUDE_CONFIG_DIR_ENVIRONMENT: match.group(1).strip()}


def file_mcp_arguments(
    all_arguments: Sequence[str], profile_directory: Path
) -> list[str]:
    """Return profile arguments with inline MCP JSON stored in a file.

    Args:
        all_arguments: The profile arguments before launcher-safe rewriting.
        profile_directory: The directory where the JSON file will be written.

    Returns:
        The rewritten profile argument list.
    """
    all_rewritten = list(all_arguments)
    for each_index, each_argument in enumerate(all_rewritten[:-1]):
        if each_argument == c.MCP_CONFIG_FLAG:
            _write_mcp_file(all_rewritten, each_index, profile_directory)
    return all_rewritten


def _write_mcp_file(
    all_rewritten: list[str], each_index: int, profile_directory: Path
) -> None:
    config_path = profile_directory / c.MCP_CONFIG_FILENAME
    config_path.write_text(all_rewritten[each_index + 1], encoding=c.TEXT_ENCODING)
    all_rewritten[each_index + 1] = str(config_path)


def claude_review_launch(
    request: ReviewRequest, launcher: Path, repository: Path, work_directory: Path
) -> tuple[list[str], str, dict[str, str]]:
    """Prepare the launcher command, review prompt, and environment.

    Args:
        request: The normalized review request.
        launcher: The selected account launcher.
        repository: The candidate repository to review.
        work_directory: The temporary directory for the profile and prompts.

    Returns:
        The launcher command, prompt text, and subprocess environment.
    """
    profile = _review_profile(launcher, work_directory)
    command = _claude_command(request, launcher, work_directory, profile)
    prompt = _review_prompt(request, repository)
    return command, prompt, _review_environment(request, profile, launcher)


def _review_profile(
    launcher: Path, work_directory: Path
) -> review_profile.ReviewProfile:
    account_environment = launcher_home(launcher)
    all_homes = review_profile.claude_homes({**os.environ, **account_environment})
    all_settings = load_settings()
    launcher_owner_home = (
        launcher.parent.joinpath(
            *[os.pardir] * len(string_list(all_settings, "launcher_directory_parts"))
        ).resolve()
        / profile_constants.DEFAULT_CLAUDE_HOME_NAME
    )
    if launcher_owner_home not in all_homes:
        all_homes = (*all_homes, launcher_owner_home)
    return review_profile.build_review_profile(
        all_homes,
        work_directory / c.PROFILE_DIRECTORY_NAME,
        Path(sys.executable),
    )


def _claude_command(
    request: ReviewRequest,
    launcher: Path,
    work_directory: Path,
    profile: review_profile.ReviewProfile,
) -> list[str]:
    command, _prompt = review_command(
        c.HARNESS_CLAUDE,
        request.model,
        request.effort,
        request.level,
        "",
        str(launcher),
        None,
        request.advisor,
        file_mcp_arguments(
            profile.all_arguments, work_directory / c.PROFILE_DIRECTORY_NAME
        ),
        _system_prompt_path(work_directory, profile),
    )
    return command


def _system_prompt_path(
    work_directory: Path, profile: review_profile.ReviewProfile
) -> Path:
    return write_system_prompt(
        work_directory / c.SYSTEM_PROMPT_FILENAME,
        run_constants.PROMPT_SECTION_SEPARATOR.join(
            (
                review_system_prompt(review_rules_text()),
                c.CONFIRMED_FINDINGS_INSTRUCTION,
            )
        ),
        profile,
    )


def _review_prompt(request: ReviewRequest, repository: Path) -> str:
    diff_completed = subprocess.run(
        ["git", *c.ALL_DIFF_ARGUMENTS, f"{request.base}...HEAD"],
        cwd=repository,
        capture_output=True,
        text=True,
        encoding=c.TEXT_ENCODING,
        errors="replace",
        check=False,
    )
    if diff_completed.returncode != 0:
        raise ReviewRequestRunFatal(
            f"git diff against base {request.base!r} failed: {diff_completed.stderr.strip()}"
        )
    return request.prompt + run_constants.CLAUDE_REVIEW_DIFF_PROMPT_TEMPLATE.format(
        diff=diff_completed.stdout
    )


def _review_environment(
    request: ReviewRequest, profile: review_profile.ReviewProfile, launcher: Path
) -> dict[str, str]:
    environment = {
        environment_name: environment_setting
        for environment_name, environment_setting in os.environ.items()
        if environment_name != c.NESTED_SESSION_ENVIRONMENT
    }
    environment.update(profile.all_environment)
    environment.update(review_profile.advisor_options(request.advisor)[1])
    environment[c.PATH_ENVIRONMENT] = os.pathsep.join(
        [str(launcher.parent), environment.get(c.PATH_ENVIRONMENT, "")]
    )
    return environment
