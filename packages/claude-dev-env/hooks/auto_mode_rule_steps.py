"""Tell whether a refused step is one of the auto mode rule flow's own steps.

The rule playbook runs its own steps after the user answers ``Allow it``. A
refusal of one of them gets no new ledger entry, so the user is never asked a
second question about the flow itself. The skip is an exact match against a
short table, and every other command gets an entry::

    python3 setup/add_auto_mode_rule.py add --label X --rule-file r.txt   -> rule step
    git push -u origin claude/auto-mode-rule-own-push   (allowed entry)    -> rule step
    git commit -m "Add the rule"   (allowed entry, HEAD on a rule branch)  -> rule step
    cd ../other && python3 setup/add_auto_mode_rule.py add ...             -> not a rule step
    git push --all origin                                                  -> not a rule step
    git -C agent-channels push -u origin claude/auto-mode-rule-own-push    -> not a rule step

A command is a rule step only when all of these hold:

- The tool is Bash and the ``cwd`` is an absolute path.
- Every character of the command is in ``ALL_SAFE_COMMAND_CHARACTERS``:
  ASCII letters, digits, a plain space, ``.``, ``_``, ``/``, ``:``, ``=``,
  ``-`` and quotes. Braces, globs, tabs and every shell operator fail.
- Its shell words match one row of ``ALL_ACCEPTED_SHAPES`` exactly.
- The ``cwd``, after ``os.path.realpath``, is the rule repository root, or a
  linked worktree of it: its ``.git`` is a plain file, not a symbolic link,
  that leads through ``commondir`` to the root's ``.git``, and the
  worktree's ``gitdir`` file points back to that same ``.git`` file.
- A git row also needs an allowed entry in the session's ledger, and the
  commit row needs that folder's ``HEAD`` on a branch that matches
  ``RULE_BRANCH_PATTERN`` in full.

A command that does not split into words, or a git file that cannot be read,
counts as not a rule step.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.auto_mode_rule_steps_constants import (
    ALL_ACCEPTED_SHAPES,
    ALL_SAFE_COMMAND_CHARACTERS,
    ANY_WORDS_TAIL,
    BASH_TOOL_NAME,
    COMMON_DIRECTORY_FILE_NAME,
    GIT_DIRECTORY_NAME,
    GIT_FILE_PREFIX,
    GITDIR_FILE_NAME,
    HEAD_FILE_NAME,
    HEAD_REF_PREFIX,
    ONE_WORD_TAIL,
    RULE_BRANCH_PATTERN,
    TEXT_ENCODING,
    AcceptedShape,
)


@dataclass(frozen=True)
class RuleFlowSetting:
    """What the skip rule needs to know about the session.

    Attributes:
        repository_root: The agent-channels checkout that holds the playbook.
        has_allowed_entry: Whether the session's ledger holds an allowed entry.
    """

    repository_root: Path
    has_allowed_entry: bool


def _command_words(command: str) -> list[str] | None:
    if not ALL_SAFE_COMMAND_CHARACTERS.issuperset(command):
        return None
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _is_rule_branch(branch_name: str | None) -> bool:
    return branch_name is not None and re.fullmatch(RULE_BRANCH_PATTERN, branch_name) is not None


def _tail_matches(tail: str, all_tail_words: list[str]) -> bool:
    if tail == ANY_WORDS_TAIL:
        return True
    if len(all_tail_words) != 1:
        return False
    return tail == ONE_WORD_TAIL or _is_rule_branch(all_tail_words[0])


def _accepted_shape_of(all_words: list[str]) -> AcceptedShape | None:
    return next(
        (
            each_shape
            for each_shape in ALL_ACCEPTED_SHAPES
            if tuple(all_words[: len(each_shape.leading_words)]) == each_shape.leading_words
            and _tail_matches(each_shape.tail, all_words[len(each_shape.leading_words) :])
        ),
        None,
    )


def _real_path(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _rule_git_directory_of(folder: Path, repository_root: Path) -> Path | None:
    repository_git_directory = _real_path(repository_root / GIT_DIRECTORY_NAME)
    if _real_path(folder) == _real_path(repository_root):
        return repository_git_directory
    git_file = _real_path(folder) / GIT_DIRECTORY_NAME
    if not git_file.is_file():
        return None
    git_file_text = git_file.read_text(encoding=TEXT_ENCODING).strip()
    if not git_file_text.startswith(GIT_FILE_PREFIX):
        return None
    linked_git_directory = _real_path(folder / git_file_text[len(GIT_FILE_PREFIX) :].strip())
    common_directory_file = linked_git_directory / COMMON_DIRECTORY_FILE_NAME
    if not common_directory_file.is_file():
        return None
    common_text = common_directory_file.read_text(encoding=TEXT_ENCODING).strip()
    if _real_path(linked_git_directory / common_text) != repository_git_directory:
        return None
    back_pointer_file = linked_git_directory / GITDIR_FILE_NAME
    if not back_pointer_file.is_file():
        return None
    back_pointer_text = back_pointer_file.read_text(encoding=TEXT_ENCODING).strip()
    if _real_path(linked_git_directory / back_pointer_text) != git_file:
        return None
    return linked_git_directory


def _head_branch_of(git_directory: Path) -> str | None:
    head_file = git_directory / HEAD_FILE_NAME
    if not head_file.is_file():
        return None
    head_text = head_file.read_text(encoding=TEXT_ENCODING).strip()
    return head_text[len(HEAD_REF_PREFIX) :] if head_text.startswith(HEAD_REF_PREFIX) else None


def _folder_fits(shape: AcceptedShape, folder: Path, repository_root: Path) -> bool:
    try:
        git_directory = _rule_git_directory_of(folder, repository_root)
        if git_directory is None:
            return False
        return not shape.needs_rule_branch_head or _is_rule_branch(_head_branch_of(git_directory))
    except (OSError, ValueError):
        return False


def is_rule_flow_step(
    tool_name: str, tool_input: object, working_folder: str | None, setting: RuleFlowSetting
) -> bool:
    """Return whether a refused call is one of the rule flow's own steps.

    Args:
        tool_name: The refused call's tool name.
        tool_input: The refused call's ``tool_input``.
        working_folder: The ``cwd`` from the hook input, or None.
        setting: The playbook's repository and the session's allowed state.

    Returns:
        Whether the call meets every condition the module docstring lists.
    """
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if tool_name != BASH_TOOL_NAME or not isinstance(command, str):
        return False
    if not working_folder or not os.path.isabs(working_folder):
        return False
    all_words = _command_words(command)
    shape = _accepted_shape_of(all_words) if all_words else None
    if shape is None or (shape.needs_allowed_entry and not setting.has_allowed_entry):
        return False
    return _folder_fits(shape, Path(working_folder), setting.repository_root)
