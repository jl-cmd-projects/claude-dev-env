"""Names the ``gh`` options that take a separate value, and the option prefix and value separator.

A reader of a ``gh`` command skips the token after each of these options, so
``gh -R o/r pr list`` reads as ``pr list`` and ``gh pr merge 12 --body -h``
reads ``-h`` as the body text. ``-f``, ``-F``, ``-H`` and ``-t`` take a value in
``gh api``, ``gh workflow run`` and ``gh pr create`` alike.
"""

from __future__ import annotations

__all__ = [
    "ALL_GH_OPTIONS_WITH_A_VALUE",
    "GH_OPTION_PREFIX",
    "GH_OPTION_VALUE_SEPARATOR",
]

ALL_GH_OPTIONS_WITH_A_VALUE: frozenset[str] = frozenset(
    {
        "-R",
        "--repo",
        "--hostname",
        "--config",
        "-H",
        "--header",
        "--head",
        "-X",
        "--method",
        "-F",
        "--field",
        "--body-file",
        "-f",
        "--raw-field",
        "--input",
        "-q",
        "--jq",
        "-t",
        "--template",
        "--title",
        "--cache",
        "--json",
        "-b",
        "--body",
        "-B",
        "--base",
        "-S",
        "--search",
        "-L",
        "--limit",
        "-s",
        "--state",
        "-l",
        "--label",
        "-a",
        "--assignee",
        "-A",
        "--author",
        "-m",
        "--milestone",
    }
)
GH_OPTION_PREFIX: str = "-"
GH_OPTION_VALUE_SEPARATOR: str = "="
