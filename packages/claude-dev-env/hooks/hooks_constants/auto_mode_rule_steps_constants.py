"""Constants for telling the auto mode rule flow's own steps apart.

``auto_mode_rule_steps.py`` skips a refused Bash command only when its words
match one row of ``ALL_ACCEPTED_SHAPES`` exactly::

    python3 setup/add_auto_mode_rule.py validate <any words>
    python3 setup/add_auto_mode_rule.py add <any words>
    git commit -m <one word>                     needs an allowed entry
    git push -u origin <rule branch>             needs an allowed entry
    git push origin <rule branch>                needs an allowed entry

A rule branch matches ``RULE_BRANCH_PATTERN`` in full.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BASH_TOOL_NAME",
    "ALL_SAFE_COMMAND_CHARACTERS",
    "GITDIR_FILE_NAME",
    "ANY_WORDS_TAIL",
    "ONE_WORD_TAIL",
    "RULE_BRANCH_TAIL",
    "AcceptedShape",
    "ALL_ACCEPTED_SHAPES",
    "RULE_BRANCH_PATTERN",
    "GIT_DIRECTORY_NAME",
    "GIT_FILE_PREFIX",
    "COMMON_DIRECTORY_FILE_NAME",
    "HEAD_FILE_NAME",
    "HEAD_REF_PREFIX",
    "TEXT_ENCODING",
]

BASH_TOOL_NAME = "Bash"
ALL_SAFE_COMMAND_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._/:=-\"'"
)

ANY_WORDS_TAIL = "any words"
ONE_WORD_TAIL = "one word"
RULE_BRANCH_TAIL = "rule branch"


@dataclass(frozen=True)
class AcceptedShape:
    """One command shape the skip rule accepts.

    Attributes:
        leading_words: The exact first words of the command.
        tail: What may follow them: any words, one word, or one rule branch.
        needs_allowed_entry: Whether the session's ledger must hold an allowed entry.
        needs_rule_branch_head: Whether the folder's ``HEAD`` must be a rule branch.
    """

    leading_words: tuple[str, ...]
    tail: str
    needs_allowed_entry: bool
    needs_rule_branch_head: bool


ALL_ACCEPTED_SHAPES = (
    AcceptedShape(
        ("python3", "setup/add_auto_mode_rule.py", "validate"), ANY_WORDS_TAIL, False, False
    ),
    AcceptedShape(("python3", "setup/add_auto_mode_rule.py", "add"), ANY_WORDS_TAIL, False, False),
    AcceptedShape(("git", "commit", "-m"), ONE_WORD_TAIL, True, True),
    AcceptedShape(("git", "push", "-u", "origin"), RULE_BRANCH_TAIL, True, False),
    AcceptedShape(("git", "push", "origin"), RULE_BRANCH_TAIL, True, False),
)

RULE_BRANCH_PATTERN = r"claude/auto-mode-rule-[a-z0-9-]+"

GIT_DIRECTORY_NAME = ".git"
GIT_FILE_PREFIX = "gitdir:"
COMMON_DIRECTORY_FILE_NAME = "commondir"
GITDIR_FILE_NAME = "gitdir"
HEAD_FILE_NAME = "HEAD"
HEAD_REF_PREFIX = "ref: refs/heads/"
TEXT_ENCODING = "utf-8"
