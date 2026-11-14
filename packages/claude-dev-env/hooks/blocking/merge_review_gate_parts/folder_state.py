"""The folder state the create walk carries: the folder, whether it is followed, and the pushed folders.

::

    cd sub        from /w            -> /w/sub
    pushd ../a    from /w            -> /w/../a, with /w pushed
    popd          after that pushd   -> /w
    cd "$X"       from /w            -> folder not followed
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_CHANGE_FOLDER_PROGRAMS,
    ALL_HOME_DEFAULT_PROGRAMS,
    ALL_PATH_PARAMETER_NAMES,
    ALL_POP_FOLDER_PROGRAMS,
    ALL_PUSH_FOLDER_PROGRAMS,
    ALL_UNFOLLOWED_FOLDER_CHARACTERS,
    HOME_FOLDER,
    OPTION_PREFIX,
    PREVIOUS_FOLDER_ARGUMENT,
)
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


@dataclass(frozen=True)
class FolderState:
    """The folder a shell is in at one point in a command.

    Attributes:
        folder: The folder in effect, or None for the gate's own.
        is_followed: False once a folder change could not be followed.
        all_pushed: The ``pushd`` stack, each entry a folder and whether it was followed.
    """

    folder: str | None
    is_followed: bool
    all_pushed: tuple[tuple[str | None, bool], ...] = ()


def state_after_folder_change(all_tokens: list[str], state: FolderState) -> FolderState:
    """Return the state after one simple command, when it changes the folder.

    ::

        ["cd", "sub"], /w           -> /w/sub
        ["cd", "-"], /w             -> folder not followed
        ["popd"], nothing pushed    -> folder not followed
        ["git", "status"], /w       -> /w

    Args:
        all_tokens: The command's tokens, with ``builtin`` and ``command`` removed.
        state: The state before the command.
    """
    program, all_arguments = segment_program_and_arguments(all_tokens)
    if program in ALL_POP_FOLDER_PROGRAMS:
        return _state_after_pop(state)
    is_push = program in ALL_PUSH_FOLDER_PROGRAMS
    if not is_push and program not in ALL_CHANGE_FOLDER_PROGRAMS:
        return state
    all_pushed = (
        (*state.all_pushed, (state.folder, state.is_followed)) if is_push else state.all_pushed
    )
    target = _folder_target(all_arguments)
    if target is None:
        target = HOME_FOLDER if program in ALL_HOME_DEFAULT_PROGRAMS else PREVIOUS_FOLDER_ARGUMENT
    folder, is_followed = _followed_folder(target, state)
    return FolderState(folder, is_followed, all_pushed)


def _state_after_pop(state: FolderState) -> FolderState:
    if not state.all_pushed:
        return FolderState(None, False)
    popped_folder, is_popped_followed = state.all_pushed[-1]
    return FolderState(popped_folder, is_popped_followed, state.all_pushed[:-1])


def _folder_target(all_arguments: list[str]) -> str | None:
    is_path_value = False
    for each_argument in all_arguments:
        word = unquoted_token(each_argument)
        if is_path_value or not word.startswith(OPTION_PREFIX) or word == PREVIOUS_FOLDER_ARGUMENT:
            return word
        is_path_value = word.lower() in ALL_PATH_PARAMETER_NAMES
    return None


def _followed_folder(target: str, state: FolderState) -> tuple[str | None, bool]:
    if target == PREVIOUS_FOLDER_ARGUMENT or ALL_UNFOLLOWED_FOLDER_CHARACTERS & set(target):
        return None, False
    target_path = Path(os.path.expanduser(target))
    if target_path.is_absolute():
        return str(target_path), True
    if not state.is_followed:
        return None, False
    return (str(Path(state.folder) / target_path) if state.folder else str(target_path)), True
