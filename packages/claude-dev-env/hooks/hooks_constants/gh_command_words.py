"""Read the command words and the standalone options of a ``gh`` call.

::

    gh -R o/r pr list --web          words ["pr", "list"], options ["-R", "--web"]
    gh api -X POST graphql           words ["api", "graphql"], options ["-X"]
    gh pr merge 12 --body -h         words ["pr", "merge", "12"], options ["--body"]

An option's separate value is neither a word nor an option, so a value that
looks like a flag, such as the ``-h`` body above, reads as text.
"""

from __future__ import annotations

from hooks_constants.gh_command_words_constants import (
    ALL_GH_OPTIONS_WITH_A_VALUE,
    GH_OPTION_PREFIX,
    GH_OPTION_VALUE_SEPARATOR,
)

__all__ = ["gh_command_words", "gh_standalone_options"]


def _gh_tokens_by_kind(all_arguments: list[str]) -> tuple[list[str], list[str]]:
    """Return the command words and the option names, skipping each option's separate value."""
    all_command_words: list[str] = []
    all_option_names: list[str] = []
    is_option_value = False
    for each_argument in all_arguments:
        is_option = not is_option_value and each_argument.startswith(GH_OPTION_PREFIX)
        if is_option:
            all_option_names.append(each_argument.split(GH_OPTION_VALUE_SEPARATOR, 1)[0])
        if not is_option and not is_option_value:
            all_command_words.append(each_argument)
        is_option_value = is_option and each_argument in ALL_GH_OPTIONS_WITH_A_VALUE
    return all_command_words, all_option_names


def gh_command_words(all_arguments: list[str]) -> list[str]:
    """Return the gh arguments that are neither an option nor an option's separate value.

    Args:
        all_arguments: The tokens after the ``gh`` program name.
    """
    return _gh_tokens_by_kind(all_arguments)[0]


def gh_standalone_options(all_arguments: list[str]) -> list[str]:
    """Return the option names a gh call sets, without any ``=value`` part or separate value.

    Args:
        all_arguments: The tokens after the ``gh`` program name.
    """
    return _gh_tokens_by_kind(all_arguments)[1]
