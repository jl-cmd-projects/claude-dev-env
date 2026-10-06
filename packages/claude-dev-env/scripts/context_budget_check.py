#!/usr/bin/env python3
"""Answer "is this context file thin enough?" and keep the over-budget list current.

::

    python context_budget_check.py path/to/SKILL.md     check files, prior = HEAD
    python context_budget_check.py --hooks              measure the policy's hooks
    python context_budget_check.py --write-baseline     rebuild the over-budget list

Run it from inside the repository whose ``.claude/context-budget.json`` applies.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import TextIO

from dev_env_scripts_constants.context_budget_check_constants import (
    ALL_GIT_ROOT_ARGUMENTS,
    ALL_LS_FILES_ARGUMENTS,
    BASELINE_WRITTEN_MESSAGE,
    CLEAN_MESSAGE,
    COMMAND_DESCRIPTION,
    FAILURE_EXIT_CODE,
    HEAD_REVISION,
    HOOK_REPORT_TEMPLATE,
    HOOKS_FLAG,
    HOOKS_HELP,
    MARKDOWN_SUFFIX,
    NO_BASELINE_TEXT,
    NO_POLICY_MESSAGE,
    PATHS_HELP,
    POLICY_RELATIVE_PATH,
    SUCCESS_EXIT_CODE,
    UTF8_ENCODING,
    WRITE_BASELINE_FLAG,
    WRITE_BASELINE_HELP,
)
from policy_lint import adapters
from policy_lint.model import ContentOrigin, Diagnostic, Document
from policy_lint.selection_git import git_bytes_for, read_blob, split_nul_tokens

_hooks_directory = str(Path(__file__).resolve().parents[1] / "hooks")
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from context_budget.baseline import build_baseline, policy_text_with_baseline
from context_budget.hook_measure import hook_findings, injected_character_count, run_hook_command
from context_budget.model import BudgetPolicy
from context_budget.policy_file import read_policy_file
from context_budget.sections import context_kind_for_path
from hooks_constants.context_budget_constants import BASELINE_FILES_KEY, BASELINE_HOOKS_KEY


def build_parser() -> argparse.ArgumentParser:
    """Return the command's argument parser.

    Returns:
        The parser for paths, ``--hooks``, and ``--write-baseline``.
    """
    parser = argparse.ArgumentParser(description=COMMAND_DESCRIPTION)
    parser.add_argument("paths", nargs="*", help=PATHS_HELP)
    parser.add_argument(HOOKS_FLAG, action="store_true", help=HOOKS_HELP)
    parser.add_argument(WRITE_BASELINE_FLAG, action="store_true", help=WRITE_BASELINE_HELP)
    return parser


def _repository_root(starting_directory: Path) -> Path:
    root_bytes = git_bytes_for(starting_directory, ALL_GIT_ROOT_ARGUMENTS)
    return Path(root_bytes.decode(UTF8_ENCODING).strip()).resolve()


def _document_for(repository_root: Path, file_path: Path) -> Document:
    relative_path = file_path.resolve().relative_to(repository_root).as_posix()
    return Document(
        PurePosixPath(relative_path),
        file_path.read_text(encoding=UTF8_ENCODING),
        read_blob(repository_root, HEAD_REVISION, relative_path),
        None,
        ContentOrigin.WORKTREE,
    )


def _diagnostics_for(repository_root: Path, file_path: Path) -> tuple[Diagnostic, ...]:
    document = _document_for(repository_root, file_path)
    if document.path.as_posix() == POLICY_RELATIVE_PATH:
        return adapters.context_budget_policy_diagnostics(document, repository_root)
    if document.path.suffix == MARKDOWN_SUFFIX:
        return adapters.context_budget_diagnostics(document, repository_root)
    return ()


def _check_paths(repository_root: Path, all_paths: Sequence[str], stdout: TextIO) -> int:
    """Check explicit files with each file's HEAD version as its prior state.

    Args:
        repository_root: Repository root holding the policy.
        all_paths: Paths given on the command line.
        stdout: Report stream.

    Returns:
        Zero when every file is within budget, else one.
    """
    all_messages = [
        each_diagnostic.message
        for each_path in all_paths
        for each_diagnostic in _diagnostics_for(repository_root, Path(each_path))
    ]
    for each_message in all_messages:
        stdout.write(each_message + "\n")
    if all_messages:
        return FAILURE_EXIT_CODE
    stdout.write(CLEAN_MESSAGE.format(count=len(all_paths)) + "\n")
    return SUCCESS_EXIT_CODE


def _measure_hooks(policy: BudgetPolicy, repository_root: Path) -> dict[str, int]:
    """Run every hook the policy lists and count the characters each injects.

    Args:
        policy: Budget policy listing the hooks.
        repository_root: Directory each hook runs from.

    Returns:
        Injected characters by hook name.
    """
    return {
        each_hook.name: injected_character_count(run_hook_command(each_hook, repository_root))
        for each_hook in policy.all_hooks
    }


def _check_hooks(policy: BudgetPolicy, repository_root: Path, stdout: TextIO) -> int:
    """Report each hook's injected characters and fail on any over budget.

    Args:
        policy: Budget policy listing the hooks.
        repository_root: Directory each hook runs from.
        stdout: Report stream.

    Returns:
        Zero when every hook is within budget, else one.
    """
    count_by_name = _measure_hooks(policy, repository_root)
    all_messages: list[str] = []
    for each_hook in policy.all_hooks:
        count = count_by_name[each_hook.name]
        baseline = policy.baseline_characters_by_hook_name.get(each_hook.name, NO_BASELINE_TEXT)
        stdout.write(
            HOOK_REPORT_TEMPLATE.format(
                name=each_hook.name, count=count, limit=each_hook.char_limit, baseline=baseline
            )
            + "\n"
        )
        all_messages.extend(hook_findings(policy, each_hook, count))
    for each_message in all_messages:
        stdout.write(each_message + "\n")
    return FAILURE_EXIT_CODE if all_messages else SUCCESS_EXIT_CODE


def current_baseline(policy: BudgetPolicy, repository_root: Path) -> dict[str, dict]:
    """Build the baseline the tracked tree and the policy's hooks need today.

    Args:
        policy: Current budget policy.
        repository_root: Repository root holding the policy.

    Returns:
        The ``baseline`` object.
    """
    all_tracked_paths = split_nul_tokens(git_bytes_for(repository_root, ALL_LS_FILES_ARGUMENTS))
    text_by_path = {
        each_path: (repository_root / each_path).read_text(encoding=UTF8_ENCODING)
        for each_path in all_tracked_paths
        if context_kind_for_path(policy, each_path) is not None
        and (repository_root / each_path).is_file()
    }
    return build_baseline(policy, text_by_path, _measure_hooks(policy, repository_root))


def _write_baseline(policy: BudgetPolicy, repository_root: Path, stdout: TextIO) -> int:
    """Rebuild the policy file's baseline from the tracked tree and its hooks.

    Args:
        policy: Current budget policy.
        repository_root: Repository root holding the policy.
        stdout: Report stream.

    Returns:
        Zero after the file is written.
    """
    baseline = current_baseline(policy, repository_root)
    policy_path = repository_root / POLICY_RELATIVE_PATH
    policy_text = policy_path.read_text(encoding=UTF8_ENCODING)
    policy_path.write_text(policy_text_with_baseline(policy_text, baseline), encoding=UTF8_ENCODING)
    file_count = len(baseline[BASELINE_FILES_KEY])
    hook_count = len(baseline[BASELINE_HOOKS_KEY])
    stdout.write(BASELINE_WRITTEN_MESSAGE.format(files=file_count, hooks=hook_count) + "\n")
    return SUCCESS_EXIT_CODE


def main(all_arguments: Sequence[str], starting_directory: Path, stdout: TextIO) -> int:
    """Run the command.

    Args:
        all_arguments: Command-line arguments.
        starting_directory: Directory inside the repository to check.
        stdout: Report stream.

    Returns:
        The exit code of the requested action.
    """
    namespace = build_parser().parse_args(list(all_arguments))
    repository_root = _repository_root(starting_directory)
    policy = read_policy_file(repository_root)
    if policy is None:
        stdout.write(NO_POLICY_MESSAGE + "\n")
        return FAILURE_EXIT_CODE
    if namespace.write_baseline:
        return _write_baseline(policy, repository_root, stdout)
    if namespace.hooks:
        return _check_hooks(policy, repository_root, stdout)
    return _check_paths(repository_root, namespace.paths, stdout)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], Path.cwd(), sys.stdout))
