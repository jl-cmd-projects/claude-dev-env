"""Deny a code commit until the repository's verify skill loads in the current turn."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.pr_lifecycle_skill_gate import (
    deny_decision,
    executable_word_lists,
    file_name,
    next_command_word,
    transcript_paths,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    GIT_GLOBAL_OPTIONS_WITH_VALUE,
    SHELL_TOOL_NAMES,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.setup_project_paths_constants import (
    DECODE_ERRORS_POLICY,
    UTF8_ENCODING,
)
from hooks_constants.verify_before_commit_gate_constants import (
    ADD_ACTION,
    ALL_ADD_EVERYTHING_OPTIONS,
    ALL_COMMIT_ALL_OPTIONS,
    ALL_COMMIT_VALUED_LONG_OPTIONS,
    ALL_COMMIT_VALUED_SHORT_FLAGS,
    ALL_DIRECTORY_CHANGE_COMMANDS,
    ALL_DIRECTORY_CHANGE_OTHER_VALUED_OPTIONS,
    ALL_DIRECTORY_CHANGE_SKIPPED_SWITCHES,
    ALL_DIRECTORY_CHANGE_TARGET_OPTIONS,
    ALL_DOCS_DATA_EXTENSIONS,
    ALL_DOCS_DIRECTORY_NAMES,
    ALL_DOCS_EXTENSIONS,
    ALL_GIT_EXECUTABLES,
    ALL_GLOB_MARKS,
    ALL_PATHSPEC_CHANGE_ARGUMENTS,
    ALL_PATHSPEC_FILE_ARGUMENTS,
    ALL_SLASH_COMMAND_MARKERS,
    ALL_STAGED_PATHS_ARGUMENTS,
    ALL_TEST_DIRECTORY_NAMES,
    ALL_TEST_FILE_INFIXES,
    ALL_TEST_FILE_NAMES,
    ALL_TEST_FILE_PREFIXES,
    ALL_TEST_FILE_SUFFIXES,
    ALL_TOP_LEVEL_ARGUMENTS,
    ALL_TRACKED_CHANGE_ARGUMENTS,
    ALL_UNEXPANDED_PATH_MARKS,
    ALL_VERIFY_SKILL_DIRECTORIES,
    ALL_WORKING_TREE_PATHS_ARGUMENTS,
    COMMIT_ACTION,
    COMMIT_ALL_SHORT_FLAG,
    DENY_REASON,
    GIT_DIRECTORY_OPTION,
    GIT_TIMEOUT_SECONDS,
    PATHSPEC_FROM_FILE_OPTION,
    PATHSPEC_TERMINATOR,
    PREVIOUS_DIRECTORY_ARGUMENT,
    SKILL_NAME,
    WHOLE_TREE_PATHSPEC,
)
from transcript_skill_scan import is_skill_loaded_since_last_prompt


@dataclass(frozen=True)
class GitCall:
    """One git command in a shell command: its directory, action, and the words after the action."""

    directory: Path
    action: str
    all_arguments: tuple[str, ...]


def _git_directory(all_global_words: list[str], base_directory: Path) -> Path:
    directory = base_directory
    for each_index, each_word in enumerate(all_global_words[:-1]):
        if each_word == GIT_DIRECTORY_OPTION:
            directory = directory / all_global_words[each_index + 1]
    return directory


def _changed_directory(all_words: list[str], directory: Path) -> Path:
    all_targets: list[str] = []
    skips_value = False
    skips_other_value = False
    for each_word in all_words[1:]:
        if skips_value:
            skips_value = False
            all_targets.append(each_word)
            continue
        option_name, colon, attached_value = each_word.partition(":")
        if option_name.lower() in ALL_DIRECTORY_CHANGE_TARGET_OPTIONS:
            if colon:
                all_targets.append(attached_value)
            else:
                skips_value = True
            continue
        if each_word.lower() in ALL_DIRECTORY_CHANGE_SKIPPED_SWITCHES:
            continue
        if each_word.lower() in ALL_DIRECTORY_CHANGE_OTHER_VALUED_OPTIONS:
            skips_other_value = True
            continue
        if skips_other_value:
            skips_other_value = False
            continue
        if each_word.startswith("-") and each_word != PREVIOUS_DIRECTORY_ARGUMENT:
            continue
        all_targets.append(each_word)
    if not all_targets:
        return Path.home()
    if all_targets[0] == PREVIOUS_DIRECTORY_ARGUMENT or any(
        each_mark in all_targets[0] for each_mark in ALL_UNEXPANDED_PATH_MARKS
    ):
        return directory
    target = directory / Path(all_targets[0]).expanduser()
    if any(each_mark in all_targets[0] for each_mark in ALL_GLOB_MARKS):
        all_matches = sorted(
            Path(target.anchor).glob(str(target.relative_to(target.anchor)))
        )
        target = all_matches[0] if all_matches else directory
    return Path(os.path.normpath(target))


def _git_calls(command: str, base_directory: Path) -> list[GitCall]:
    all_calls: list[GitCall] = []
    all_base_directories = [base_directory]
    for each_words in executable_word_lists(command):
        if file_name(each_words[0]) in ALL_DIRECTORY_CHANGE_COMMANDS:
            all_base_directories.extend(
                each_changed
                for each_changed in dict.fromkeys(
                    _changed_directory(each_words, each_directory)
                    for each_directory in all_base_directories
                )
                if each_changed not in all_base_directories
            )
            continue
        if file_name(each_words[0]) not in ALL_GIT_EXECUTABLES:
            continue
        action, after_action = next_command_word(
            each_words, 1, GIT_GLOBAL_OPTIONS_WITH_VALUE
        )
        if action is None:
            continue
        all_calls.extend(
            GitCall(
                _git_directory(each_words[1 : after_action - 1], each_directory),
                action,
                tuple(each_words[after_action:]),
            )
            for each_directory in all_base_directories
        )
    return all_calls


def _git_lines(directory: Path, all_arguments: Iterable[str]) -> list[str] | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(directory), *all_arguments],
            capture_output=True,
            text=True,
            encoding=UTF8_ENCODING,
            errors=DECODE_ERRORS_POLICY,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return [each_line for each_line in completed.stdout.splitlines() if each_line]


def _short_flag_cluster(cluster: str) -> tuple[bool, bool]:
    for each_flag in cluster[1:]:
        if each_flag == COMMIT_ALL_SHORT_FLAG:
            return True, False
        if each_flag in ALL_COMMIT_VALUED_SHORT_FLAGS:
            return False, cluster.endswith(each_flag)
    return False, False


def _commits_all_tracked_changes(all_arguments: tuple[str, ...]) -> bool:
    skips_value = False
    for each_word in all_arguments:
        if skips_value:
            skips_value = False
            continue
        if each_word == PATHSPEC_TERMINATOR:
            return False
        if each_word in ALL_COMMIT_ALL_OPTIONS:
            return True
        is_short_cluster = each_word.startswith("-") and not each_word.startswith("--")
        commits_all, skips_value = _short_flag_cluster(each_word) if is_short_cluster else (False, False)
        if commits_all:
            return True
    return False


def _short_cluster_takes_value(cluster: str) -> bool:
    for each_index, each_flag in enumerate(cluster[1:], start=1):
        if each_flag in ALL_COMMIT_VALUED_SHORT_FLAGS:
            return each_index == len(cluster) - 1
    return False


def _commit_pathspecs(all_arguments: tuple[str, ...]) -> list[str]:
    all_pathspecs: list[str] = []
    skips_value = False
    for each_index, each_word in enumerate(all_arguments):
        if skips_value:
            skips_value = False
            continue
        if each_word == PATHSPEC_TERMINATOR:
            all_pathspecs.extend(all_arguments[each_index + 1 :])
            break
        if each_word.startswith(PATHSPEC_FROM_FILE_OPTION):
            return [WHOLE_TREE_PATHSPEC]
        if each_word.startswith("--"):
            skips_value = each_word in ALL_COMMIT_VALUED_LONG_OPTIONS
            continue
        if each_word.startswith("-") and len(each_word) > 1:
            skips_value = _short_cluster_takes_value(each_word)
            continue
        all_pathspecs.append(each_word)
    return all_pathspecs


def _added_pathspecs(all_arguments: tuple[str, ...]) -> list[str]:
    terminator_index = (
        all_arguments.index(PATHSPEC_TERMINATOR) if PATHSPEC_TERMINATOR in all_arguments else len(all_arguments)
    )
    all_option_words = all_arguments[:terminator_index]
    all_pathspecs = [each_word for each_word in all_option_words if not each_word.startswith("-")]
    all_pathspecs.extend(all_arguments[terminator_index + 1 :])
    if not all_pathspecs and any(each_word in ALL_ADD_EVERYTHING_OPTIONS for each_word in all_option_words):
        return [WHOLE_TREE_PATHSPEC]
    return all_pathspecs


def _committed_paths(
    commit: GitCall, all_earlier_calls: list[GitCall]
) -> set[str] | None:
    staged_paths = _git_lines(commit.directory, ALL_STAGED_PATHS_ARGUMENTS)
    if staged_paths is None:
        return None
    all_paths = set(staged_paths)
    all_commit_pathspecs = _commit_pathspecs(commit.all_arguments)
    if all_commit_pathspecs:
        pathspec_paths = _git_lines(
            commit.directory, (*ALL_PATHSPEC_CHANGE_ARGUMENTS, *all_commit_pathspecs)
        )
        if pathspec_paths is None:
            pathspec_paths = _git_lines(
                commit.directory, (*ALL_PATHSPEC_FILE_ARGUMENTS, *all_commit_pathspecs)
            )
        all_paths.update(pathspec_paths or [])
    if _commits_all_tracked_changes(commit.all_arguments):
        all_paths.update(
            _git_lines(commit.directory, ALL_TRACKED_CHANGE_ARGUMENTS) or []
        )
    for each_call in all_earlier_calls:
        if each_call.action != ADD_ACTION or each_call.directory != commit.directory:
            continue
        all_pathspecs = _added_pathspecs(each_call.all_arguments)
        if all_pathspecs:
            all_working_tree_arguments = (
                *ALL_WORKING_TREE_PATHS_ARGUMENTS,
                *all_pathspecs,
            )
            all_paths.update(
                _git_lines(each_call.directory, all_working_tree_arguments) or []
            )
    return all_paths


def _is_docs_or_test_path(repository_path: str) -> bool:
    path = PurePosixPath(repository_path)
    if path.suffix.lower() in ALL_DOCS_EXTENSIONS or path.name in ALL_TEST_FILE_NAMES:
        return True
    all_directory_parts = path.parts[:-1]
    if path.suffix.lower() in ALL_DOCS_DATA_EXTENSIONS and any(
        each_part in ALL_DOCS_DIRECTORY_NAMES for each_part in all_directory_parts
    ):
        return True
    if any(each_part in ALL_TEST_DIRECTORY_NAMES for each_part in all_directory_parts):
        return True
    return (
        path.name.startswith(ALL_TEST_FILE_PREFIXES)
        or path.name.endswith(ALL_TEST_FILE_SUFFIXES)
        or any(each_infix in path.name for each_infix in ALL_TEST_FILE_INFIXES)
    )


def _has_verify_skill(directory: Path) -> bool:
    top_level = _git_lines(directory, ALL_TOP_LEVEL_ARGUMENTS)
    if not top_level:
        return False
    repository_root = Path(top_level[0])
    return any(
        (repository_root / each_directory).is_dir()
        for each_directory in ALL_VERIFY_SKILL_DIRECTORIES
    )


def _verify_load_status(transcript_path: str) -> bool | None:
    try:
        with open(
            transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY
        ) as transcript:
            return is_skill_loaded_since_last_prompt(
                transcript, (SKILL_NAME,), ALL_SLASH_COMMAND_MARKERS
            )
    except OSError:
        return None


def _is_verified_or_unreadable(all_payload_fields: dict[str, object]) -> bool:
    all_paths = transcript_paths(all_payload_fields)
    if not all_paths:
        return True
    return any(_verify_load_status(each_path) is not False for each_path in all_paths)


def _commits_code(all_git_calls: list[GitCall]) -> bool:
    for each_index, each_call in enumerate(all_git_calls):
        if each_call.action != COMMIT_ACTION or not _has_verify_skill(
            each_call.directory
        ):
            continue
        all_paths = _committed_paths(each_call, all_git_calls[:each_index])
        if all_paths and not all(
            _is_docs_or_test_path(each_path) for each_path in all_paths
        ):
            return True
    return False


def _shell_command(all_payload_fields: dict[str, object]) -> str | None:
    if all_payload_fields.get("tool_name") not in SHELL_TOOL_NAMES:
        return None
    tool_input = all_payload_fields.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return command if isinstance(command, str) else None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a code commit made before the verify skill loads this turn, else None.

    ::

        git commit, code staged, no verify since the last prompt      -> DENY_REASON
        git add app.py; git commit, empty index, no verify            -> DENY_REASON
        git commit app.py, app.py changed but not staged              -> DENY_REASON
        git commit README.md, code staged                             -> DENY_REASON
        cd <repo> && git commit -am x, from another directory         -> DENY_REASON
        git commit, only docs or test files                           -> None
        git commit, only data files (.json, .jsonl, .yaml, .yml,
            .csv) under a docs folder                                 -> None
        git commit, a .py file under a docs folder                    -> DENY_REASON
        git commit after a verify Skill call or a /verify prompt      -> None
        git commit in a repository with no verify skill directory     -> None
        transcript missing or unreadable, or git fails                -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    command = _shell_command(all_payload_fields)
    if command is None:
        return None
    working_directory = all_payload_fields.get("cwd")
    base_directory = (
        Path(working_directory) if isinstance(working_directory, str) else Path.cwd()
    )
    all_git_calls = _git_calls(command, base_directory)
    if not any(each_call.action == COMMIT_ACTION for each_call in all_git_calls):
        return None
    if _is_verified_or_unreadable(all_payload_fields) or not _commits_code(
        all_git_calls
    ):
        return None
    return deny_decision(DENY_REASON)


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
