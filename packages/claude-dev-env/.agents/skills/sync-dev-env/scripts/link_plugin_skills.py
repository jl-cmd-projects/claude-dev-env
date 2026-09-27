#!/usr/bin/env python3
"""Link every enabled plugin's skills into the user skills directory.

::

    ~/.claude/skills/tdd -> ~/.claude/plugins/cache/<market>/<plugin>/<version>/skills/tdd
    ok:   no entry named tdd           -> link created
    ok:   owned link at an old version -> link re-pointed
    ok:   owned link, skill now gone   -> link removed
    flag: a user skill named tdd       -> left in place, reported as skipped

A link is owned when it points inside the plugin cache.
A running session reads the skills directory live, so the linked skills load at once.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

scripts_directory = str(Path(__file__).resolve().parent)
if scripts_directory not in sys.path:
    sys.path.insert(0, scripts_directory)

from sync_dev_env_constants.config.constants import (
    CREATED_REPORT,
    DEFAULT_CLAUDE_HOME,
    ENABLED_PLUGINS_KEY,
    INSTALL_PATH_KEY,
    INSTALLED_PLUGINS_RELATIVE_PATH,
    KEPT_OUTCOME,
    LAST_UPDATED_KEY,
    LINKED_OUTCOME,
    PLUGIN_CACHE_RELATIVE_PATH,
    PLUGINS_KEY,
    REMOVED_OUTCOME,
    REMOVED_REPORT,
    REPOINTED_OUTCOME,
    REPOINTED_REPORT,
    SETTINGS_FILE_NAME,
    SKILL_MANIFEST_FILE_NAME,
    SKILLS_DIRECTORY_NAME,
    SKIPPED_OUTCOME,
    SKIPPED_REPORT,
    SUMMARY_REPORT,
)


def read_json_file(from_path: Path) -> dict:
    """Read one JSON settings file.

    Args:
        from_path: The JSON file to read.

    Returns:
        The parsed object, or an empty dict when the file is absent.
    """
    if not from_path.is_file():
        return {}
    return json.loads(from_path.read_text(encoding="utf-8"))


def enabled_install_paths(claude_home: Path) -> list[Path]:
    """List the newest install directory of every plugin the user settings enable.

    Args:
        claude_home: The Claude Code home directory.

    Returns:
        One install directory per enabled plugin that has an install record.
    """
    enabled_by_plugin = read_json_file(claude_home / SETTINGS_FILE_NAME).get(ENABLED_PLUGINS_KEY, {})
    records_by_plugin = read_json_file(claude_home / INSTALLED_PLUGINS_RELATIVE_PATH).get(PLUGINS_KEY, {})
    all_install_paths = []
    for each_plugin, each_record_list in records_by_plugin.items():
        if enabled_by_plugin.get(each_plugin) is not True or not each_record_list:
            continue
        newest_record = max(each_record_list, key=lambda each_record: each_record.get(LAST_UPDATED_KEY, ""))
        all_install_paths.append(Path(newest_record[INSTALL_PATH_KEY]))
    return all_install_paths


def skill_directories_of(install_path: Path) -> list[Path]:
    """List the skill directories one plugin install ships.

    Args:
        install_path: The plugin install directory.

    Returns:
        Each subdirectory of the install's skills directory that holds a SKILL.md.
    """
    skills_root = install_path / SKILLS_DIRECTORY_NAME
    if not skills_root.is_dir():
        return []
    return [
        each_directory
        for each_directory in sorted(skills_root.iterdir())
        if (each_directory / SKILL_MANIFEST_FILE_NAME).is_file()
    ]


def desired_skill_targets(claude_home: Path) -> dict[str, Path]:
    """Map each enabled plugin skill name to the directory its link points at.

    Args:
        claude_home: The Claude Code home directory.

    Returns:
        The target directory by skill name. The first plugin to ship a name keeps it.
    """
    target_by_name: dict[str, Path] = {}
    for each_install_path in enabled_install_paths(claude_home):
        for each_directory in skill_directories_of(each_install_path):
            target_by_name.setdefault(each_directory.name, each_directory)
    return target_by_name


def is_owned_link(entry: Path, plugin_cache: Path) -> bool:
    """Report whether an entry is a symlink that points inside the plugin cache.

    Args:
        entry: One entry of the skills directory.
        plugin_cache: The resolved plugin cache directory.

    Returns:
        True when the entry is a symlink whose target lies under the plugin cache.
    """
    if not entry.is_symlink():
        return False
    link_target = Path(os.path.normpath(entry.parent / os.readlink(entry)))
    return link_target.is_relative_to(plugin_cache)


def sync_links(claude_home: Path) -> Counter:
    """Converge the skills directory on one link per enabled plugin skill.

    Args:
        claude_home: The Claude Code home directory.

    Returns:
        The count of each outcome name across every entry the run touched.
    """
    skills_directory = Path(os.path.realpath(claude_home / SKILLS_DIRECTORY_NAME))
    skills_directory.mkdir(parents=True, exist_ok=True)
    plugin_cache = Path(os.path.realpath(claude_home / PLUGIN_CACHE_RELATIVE_PATH))
    target_by_name = desired_skill_targets(claude_home)
    outcome_counts: Counter = Counter()
    for each_entry in sorted(skills_directory.iterdir()):
        if is_owned_link(each_entry, plugin_cache) and each_entry.name not in target_by_name:
            each_entry.unlink()
            print(REMOVED_REPORT.format(name=each_entry.name))
            outcome_counts[REMOVED_OUTCOME] += 1
    for each_name, each_target in sorted(target_by_name.items()):
        outcome_counts[link_one_skill(skills_directory / each_name, each_target, plugin_cache)] += 1
    return outcome_counts


def link_one_skill(link_path: Path, target: Path, plugin_cache: Path) -> str:
    """Create or re-point one owned link, leaving any other entry of that name alone.

    Args:
        link_path: Where the link belongs in the skills directory.
        target: The plugin skill directory the link points at.
        plugin_cache: The resolved plugin cache directory.

    Returns:
        The outcome name: linked, repointed, kept, or skipped.
    """
    if is_owned_link(link_path, plugin_cache):
        if os.readlink(link_path) == str(target):
            return KEPT_OUTCOME
        link_path.unlink()
        link_path.symlink_to(target, target_is_directory=True)
        print(REPOINTED_REPORT.format(name=link_path.name, target=target))
        return REPOINTED_OUTCOME
    if link_path.exists() or link_path.is_symlink():
        print(SKIPPED_REPORT.format(name=link_path.name))
        return SKIPPED_OUTCOME
    link_path.symlink_to(target, target_is_directory=True)
    print(CREATED_REPORT.format(name=link_path.name, target=target))
    return LINKED_OUTCOME


def main() -> int:
    """Parse the Claude home from the command line, sync the links, and print a summary.

    Returns:
        0 after printing the summary line.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-home", type=Path, default=DEFAULT_CLAUDE_HOME)
    parsed_arguments = parser.parse_args()
    outcome_counts = sync_links(parsed_arguments.claude_home)
    print(
        SUMMARY_REPORT.format(
            linked=outcome_counts[LINKED_OUTCOME],
            repointed=outcome_counts[REPOINTED_OUTCOME],
            removed=outcome_counts[REMOVED_OUTCOME],
            skipped=outcome_counts[SKIPPED_OUTCOME],
            kept=outcome_counts[KEPT_OUTCOME],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
