"""Step over the wrappers in front of a shell command to reach the command it runs.

A wrapper either runs its own operands, as ``sudo``, ``xargs``, ``env``, and
``timeout`` do, or runs a command string, as ``bash -c``, ``sh -lc``, and
``pwsh -Command`` do::

    sudo git push                         git, ["push"]
    env GIT_DIR=x git push                git, ["push"]
    echo origin | xargs git push          git, ["push"]
    bash -lc "git commit -F m.txt"        "git commit -F m.txt" unwraps in turn

``pytest_invocation`` owns the wrapper and string-exec parsing, and this module
composes it into the two answers a hook asks about any program.
"""

from __future__ import annotations

from hooks_constants.pytest_invocation import (
    all_tokens_after_wrappers,
    string_exec_inner_command,
    unquoted_token,
)
from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
from hooks_constants.shell_command_segments import (
    effective_leading_program,
    token_basename,
)

__all__ = [
    "segment_program_and_arguments",
    "all_wrapped_command_texts",
]


def segment_program_and_arguments(all_segment_tokens: list[str]) -> tuple[str, list[str]]:
    """Return a segment's program basename past its wrappers and the tokens after it.

    Returns an empty pair when the segment names no program.
    """
    all_unwrapped_tokens = all_tokens_after_wrappers(all_segment_tokens)
    program_token = effective_leading_program(all_unwrapped_tokens)
    if program_token is None:
        return "", []
    program_index = all_unwrapped_tokens.index(program_token)
    return token_basename(unquoted_token(program_token)), all_unwrapped_tokens[program_index + 1 :]


def all_wrapped_command_texts(command: str) -> list[str]:
    """Return the command plus the command string every shell wrapper inside it runs.

    The segments come from the quote-aware pipeline parser, so the quoted
    script in ``powershell -Command "git add -A; git push"`` stays whole until
    its own turn. Nested wrappers unwrap in turn.
    """
    all_inner_commands = [
        string_exec_inner_command(each_segment)
        for each_segment, _following_operator in pipeline_segments_for_command(command)
    ]
    all_command_texts = [command]
    for each_inner_command in all_inner_commands:
        if each_inner_command is not None:
            all_command_texts.extend(all_wrapped_command_texts(each_inner_command))
    return all_command_texts
