"""Build a bare-like Claude profile for headless code reviews."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.config import review_profile_constants as c
from tools.force_remove import force_remove_tree

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewProfile:
    all_arguments: tuple[str, ...]
    all_environment: Mapping[str, str]
    standards_path: Path


def claude_homes(all_variables: Mapping[str, str]) -> tuple[Path, ...]:
    """Return the Claude homes to read, the account home first, then the main home.

    Args:
        all_variables: The process environment.

    Returns:
        The account home, its owner's main home, and the runner's main home.
    """
    main_home = Path.home() / c.DEFAULT_CLAUDE_HOME_NAME
    configured = all_variables.get(c.CLAUDE_CONFIG_DIR_ENVIRONMENT)
    if not configured or Path(configured) == main_home:
        return (main_home,)
    account_home = Path(configured)
    all_homes = [account_home]
    if account_home.parent.name == c.ACCOUNT_PROFILES_DIRECTORY_NAME:
        all_homes.append(account_home.parent.parent / c.DEFAULT_CLAUDE_HOME_NAME)
    all_homes.append(main_home)
    return tuple(dict.fromkeys(all_homes))


def installed_plugin_path(all_homes: Sequence[Path], plugin_key: str) -> Path:
    """Return the install folder of the newest installed copy of one plugin.

    Args:
        all_homes: Claude homes to search, in order.
        plugin_key: The plugin key, such as marketplace plugin id.

    Returns:
        The install directory.

    Raises:
        FileNotFoundError: No home has an install record or a cached copy.
    """
    recorded = _recorded_plugin_path(all_homes, plugin_key)
    if recorded is not None:
        return recorded
    cached = _cached_plugin_path(all_homes, plugin_key)
    if cached is not None:
        return cached
    homes = c.HOME_LIST_SEPARATOR.join(str(each_home) for each_home in all_homes)
    raise FileNotFoundError(
        c.MISSING_PLUGIN_MESSAGE.format(plugin=plugin_key, homes=homes)
    )


def _recorded_plugin_path(all_homes: Sequence[Path], plugin_key: str) -> Path | None:
    for each_home in all_homes:
        found = _record_install_path(each_home, plugin_key)
        if found is not None:
            return found
    return None


def _record_install_path(home: Path, plugin_key: str) -> Path | None:
    record_path = home.joinpath(*c.ALL_INSTALLED_PLUGINS_RELATIVE_PATH)
    if not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding=c.JSON_READ_ENCODING))
    all_installs = record.get(c.INSTALLED_PLUGINS_KEY, {}).get(plugin_key)
    if not all_installs:
        return None
    return Path(all_installs[-1][c.INSTALL_PATH_KEY])


def _cached_plugin_path(all_homes: Sequence[Path], plugin_key: str) -> Path | None:
    plugin_name, _, marketplace = plugin_key.partition(c.PLUGIN_KEY_SEPARATOR)
    for each_home in all_homes:
        found = _newest_cached_plugin(each_home, marketplace, plugin_name)
        if found is not None:
            return found
    return None


def _newest_cached_plugin(home: Path, marketplace: str, plugin_name: str) -> Path | None:
    versions_directory = home.joinpath(
        *c.ALL_PLUGIN_CACHE_RELATIVE_PATH, marketplace, plugin_name
    )
    if not versions_directory.is_dir():
        return None
    all_cached = [
        each_version
        for each_version in versions_directory.iterdir()
        if (each_version / c.PLUGIN_MANIFEST_DIRECTORY).is_dir()
    ]
    if not all_cached:
        return None
    return max(all_cached, key=_version_order)


def _version_order(
    version_directory: Path,
) -> tuple[tuple[int, ...], bool, tuple[tuple[bool, int, str], ...]]:
    version = version_directory.name.partition("+")[0]
    release, separator, prerelease = version.partition("-")
    all_release_parts = tuple(
        int(each_part) if each_part.isdigit() else -1
        for each_part in release.split(".")
    )
    all_prerelease_parts = tuple(
        (False, int(each_part), "") if each_part.isdigit() else (True, 0, each_part)
        for each_part in prerelease.split(".")
    )
    return all_release_parts, not separator, all_prerelease_parts


def write_trimmed_plugin(source: Path, destination: Path) -> Path:
    """Copy the plugin manifest, the kept review skills, and every principle skill.

    Args:
        source: The installed plugin directory.
        destination: The profile directory that receives the copy.

    Returns:
        The destination directory.
    """
    if destination.exists():
        force_remove_tree(destination)
    shutil.copytree(
        source / c.PLUGIN_MANIFEST_DIRECTORY,
        destination / c.PLUGIN_MANIFEST_DIRECTORY,
        dirs_exist_ok=True,
    )
    for each_skill in sorted((source / c.PLUGIN_SKILLS_DIRECTORY).iterdir()):
        _copy_kept_skill(each_skill, destination)
    return destination


def _copy_kept_skill(each_skill: Path, destination: Path) -> None:
    is_kept = (
        each_skill.name in c.ALL_KEPT_PSTACK_SKILLS
        or each_skill.name.startswith(c.PRINCIPLE_SKILL_PREFIX)
    )
    if is_kept and each_skill.is_dir():
        shutil.copytree(
            each_skill,
            destination / c.PLUGIN_SKILLS_DIRECTORY / each_skill.name,
            dirs_exist_ok=True,
        )


def profile_settings(instructions_path: Path, python_path: Path) -> dict:
    """Return settings that turn off unused bundled skills and add compaction instructions.

    Args:
        instructions_path: The compaction instructions file.
        python_path: The interpreter the compaction hook runs.

    Returns:
        The settings mapping written into the profile.
    """
    hook_command = c.COMPACT_HOOK_COMMAND_TEMPLATE.format(
        python=python_path.as_posix(), instructions=instructions_path.as_posix()
    )
    return {
        "enabledPlugins": {},
        "autoMemoryEnabled": False,
        "autoCompactWindow": c.AUTOCOMPACT_WINDOW_TOKENS,
        "skillOverrides": {
            each_skill: c.SKILL_OFF for each_skill in c.ALL_DISABLED_BUNDLED_SKILLS
        },
        "permissions": {"blockReadsOutsideWorkingDirectories": True},
        "hooks": {
            c.PRE_COMPACT_EVENT: [
                {"matcher": "", "hooks": [{"type": "command", "command": hook_command}]}
            ]
        },
    }


def standards_text(all_homes: Sequence[Path]) -> str:
    """Return the code standards, one tagged block per file.

    Args:
        all_homes: Claude homes to read, in order.

    Returns:
        The standards text. A file no home has is left out.
    """
    all_blocks = [c.STANDARDS_HEADING]
    for each_parts in c.ALL_STANDARD_RELATIVE_PATHS:
        _append_standard(all_blocks, all_homes, each_parts)
    return c.STANDARDS_BLOCK_GAP.join(all_blocks) + c.LINE_SEPARATOR


def _append_standard(
    all_blocks: list[str], all_homes: Sequence[Path], all_parts: Sequence[str]
) -> None:
    standard_path = next(
        (
            each_home.joinpath(*all_parts)
            for each_home in all_homes
            if each_home.joinpath(*all_parts).is_file()
        ),
        None,
    )
    if standard_path is None:
        return
    all_blocks.append(
        c.STANDARD_BLOCK_TEMPLATE.format(
            name=standard_path.name,
            text=standard_path.read_text(encoding=c.TEXT_ENCODING).strip(),
        )
    )


def build_review_profile(
    all_homes: Sequence[Path], profile_directory: Path, python_path: Path
) -> ReviewProfile:
    """Write the profile files and return the CLI arguments and environment that load them.

    Args:
        all_homes: The Claude homes to read, in order.
        profile_directory: A folder outside the reviewed checkout.
        python_path: The interpreter the compaction hook runs.

    Returns:
        The arguments, the environment, and the standards file.
    """
    profile_directory.mkdir(parents=True, exist_ok=True)
    plugin_directory = write_trimmed_plugin(
        installed_plugin_path(all_homes, c.PSTACK_PLUGIN_KEY),
        profile_directory / c.PLUGIN_DIRECTORY_NAME,
    )
    settings_path, standards_path = _write_profile_files(
        all_homes, profile_directory, python_path
    )
    return ReviewProfile(
        all_arguments=_profile_arguments(settings_path, plugin_directory),
        all_environment=dict(c.ALL_PROFILE_ENVIRONMENT),
        standards_path=standards_path,
    )


def _write_profile_files(
    all_homes: Sequence[Path], profile_directory: Path, python_path: Path
) -> tuple[Path, Path]:
    instructions_path = profile_directory / c.COMPACT_INSTRUCTIONS_FILENAME
    instructions_path.write_text(c.COMPACT_INSTRUCTIONS, encoding=c.TEXT_ENCODING)
    settings_path = profile_directory / c.SETTINGS_FILENAME
    settings_path.write_text(
        json.dumps(profile_settings(instructions_path, python_path), indent=c.JSON_INDENT),
        encoding=c.TEXT_ENCODING,
    )
    standards_path = profile_directory / c.STANDARDS_FILENAME
    standards_path.write_text(standards_text(all_homes), encoding=c.TEXT_ENCODING)
    return settings_path, standards_path


def _profile_arguments(settings_path: Path, plugin_directory: Path) -> tuple[str, ...]:
    return (
        "--setting-sources",
        c.LOCAL_SETTING_SOURCE,
        "--settings",
        str(settings_path),
        "--plugin-dir",
        str(plugin_directory),
        "--strict-mcp-config",
        "--mcp-config",
        c.EMPTY_MCP_CONFIG,
        "--autocompact",
        c.AUTOCOMPACT_WINDOW,
    )


def advisor_options(advisor: str) -> tuple[tuple[str, ...], dict[str, str]]:
    """Return the advisor flag and environment for one advisor choice.

    Args:
        advisor: An advisor model family, or none.

    Returns:
        The extra arguments and the extra environment.
    """
    if advisor == c.ADVISOR_OFF:
        return (), dict(c.ALL_ADVISOR_OFF_ENVIRONMENT)
    return ("--advisor", advisor), {}


def main() -> int:
    """Write one profile and print its arguments.

    Returns:
        Zero after the profile is written.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    return _write_profile_from_arguments()


def _write_profile_from_arguments() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--advisor", default=c.ADVISOR_OFF)
    parsed = parser.parse_args()
    profile = build_review_profile(
        claude_homes(os.environ), parsed.output, Path(sys.executable)
    )
    all_advisor_arguments, all_advisor_environment = advisor_options(parsed.advisor)
    logger.info(
        "%s",
        json.dumps(
            {
                "arguments": [
                    *profile.all_arguments,
                    "--append-system-prompt-file",
                    str(profile.standards_path),
                    *all_advisor_arguments,
                ],
                "environment": {**profile.all_environment, **all_advisor_environment},
            },
            indent=c.JSON_INDENT,
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
