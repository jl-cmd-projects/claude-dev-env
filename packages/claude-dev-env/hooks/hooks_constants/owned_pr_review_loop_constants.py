"""Constants for the owned pull request review-loop context hook.

The hook is a PostToolUse observer. It never blocks. After the agent opens a
pull request on a repository we own, outside the preset list of repositories
that run their own automated review, it tells the agent to own an efficient
review loop and drive the pull request through to merge.

Private owner and repository names stay out of this public tree. Each set holds the
SHA-256 digest of a name normalized to lower-case ASCII letters and digits,
the same form ``scripts/private_terms.py`` uses::

    "Acme-Widgets"          -> "acmewidgets"
    "Acme-Widgets/tools"    -> "acmewidgetstools"

To add an owner or a preset repository, append the digest of its normalized
form.
"""

from __future__ import annotations

import re

__all__ = [
    "NAME_DIGEST_TEXT_ENCODING",
    "ALL_OWNED_OWNER_DIGESTS",
    "ALL_PRESET_REPOSITORY_DIGESTS",
    "ALL_SHELL_TOOL_NAMES",
    "ALL_SHELL_COMMAND_INPUT_KEYS",
    "SHELL_ARGUMENT_SEPARATOR",
    "ALL_GH_PR_CREATE_ACTIONS",
    "GH_PROGRAM_NAME",
    "GH_PR_SUBCOMMAND",
    "GH_API_SUBCOMMAND",
    "GH_API_PULLS_ENDPOINT_PATTERN",
    "ALL_GH_API_BODY_OPTIONS",
    "ALL_GH_API_METHOD_OPTIONS",
    "GH_API_POST_METHOD",
    "GH_LONG_OPTION_PREFIX",
    "GH_SHORT_OPTION_LENGTH",
    "ALL_GH_API_SHORT_OPTIONS",
    "GH_OPTION_VALUE_SEPARATOR",
    "PYTHON_OPTION_PREFIX",
    "PYTHON_SHORT_OPTION_LENGTH",
    "PYTHON_OPTION_AND_VALUE_WORD_COUNT",
    "ALL_PYTHON_SCRIPTLESS_OPTIONS",
    "BACKSLASH",
    "DOUBLED_BACKSLASH",
    "MCP_TOOL_NAME_PREFIX",
    "ALL_MCP_CREATE_PULL_REQUEST_TOOL_SUFFIXES",
    "MCP_OWNER_INPUT_KEY",
    "MCP_REPOSITORY_INPUT_KEY",
    "PULL_REQUEST_URL_PATTERN",
    "ALREADY_EXISTS_MARKER",
    "ALL_DECLARED_URL_KEYS",
    "JSON_OBJECT_OPENER",
    "REVIEW_LOOP_CONTEXT_TEMPLATE",
    "SESSION_RECORD_FILE_TEMPLATE",
    "SESSION_RECORD_TEMPORARY_PREFIX",
    "ALL_PULL_REQUEST_FIELD_NAMES",
]

NAME_DIGEST_TEXT_ENCODING: str = "utf-8"
ALL_OWNED_OWNER_DIGESTS: frozenset[str] = frozenset(
    {
        "2e8b9d88060d471690c122e6843f3bec8c95116d643af2f5501e0881b10e83c4",
        "3a92fc8d256dc1f50dc8794573f80de695516f0f0e5c235118bd0c18be3d4434",
        "d526db5593d5986500e4770cb6018f2d33c459ed93657487958a6086e52e6147",
        "95d4d8808440e130d0ee753e0b7530eba4534dd41a7320ad8b710a44d40441f4",
    }
)
ALL_PRESET_REPOSITORY_DIGESTS: frozenset[str] = frozenset(
    {"d362bee4d80f5474921b917c127f2b0680c0a5261cb352e59de35cc87b00989f"}
)

ALL_SHELL_TOOL_NAMES: frozenset[str] = frozenset(
    {"Bash", "PowerShell", "exec_command", "shell_command"}
)
ALL_SHELL_COMMAND_INPUT_KEYS: tuple[str, ...] = ("command", "cmd")
SHELL_ARGUMENT_SEPARATOR: str = " "
GH_PROGRAM_NAME: str = "gh"
GH_PR_SUBCOMMAND: str = "pr"
ALL_GH_PR_CREATE_ACTIONS: frozenset[str] = frozenset({"create", "new"})
GH_API_SUBCOMMAND: str = "api"
GH_API_PULLS_ENDPOINT_PATTERN: re.Pattern[str] = re.compile(r"/?repos/[^/\s]+/[^/\s]+/pulls")
ALL_GH_API_BODY_OPTIONS: frozenset[str] = frozenset(
    {"-f", "-F", "--field", "--raw-field", "--input"}
)
ALL_GH_API_METHOD_OPTIONS: frozenset[str] = frozenset({"-X", "--method"})
GH_API_POST_METHOD: str = "POST"
GH_LONG_OPTION_PREFIX: str = "--"
GH_SHORT_OPTION_LENGTH: int = 2
ALL_GH_API_SHORT_OPTIONS: frozenset[str] = frozenset({"-f", "-F", "-X"})
GH_OPTION_VALUE_SEPARATOR: str = "="
PYTHON_OPTION_PREFIX: str = "-"
PYTHON_SHORT_OPTION_LENGTH: int = 2
PYTHON_OPTION_AND_VALUE_WORD_COUNT: int = 2
ALL_PYTHON_SCRIPTLESS_OPTIONS: frozenset[str] = frozenset({"-m", "-c"})
BACKSLASH: str = "\\"
DOUBLED_BACKSLASH: str = "\\\\"

MCP_TOOL_NAME_PREFIX: str = "mcp__"
ALL_MCP_CREATE_PULL_REQUEST_TOOL_SUFFIXES: tuple[str, ...] = (
    "__create_pull_request",
    "__github_create_pull_request",
)
MCP_OWNER_INPUT_KEY: str = "owner"
MCP_REPOSITORY_INPUT_KEY: str = "repo"

PULL_REQUEST_URL_PATTERN: re.Pattern[str] = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/"
    r"(?P<repository>[A-Za-z0-9._-]+)/pull/(?P<number>\d+)"
)
ALREADY_EXISTS_MARKER: str = "already exists"
ALL_DECLARED_URL_KEYS: tuple[str, ...] = ("html_url", "url")
JSON_OBJECT_OPENER: str = "{"

SESSION_RECORD_FILE_TEMPLATE: str = "owned-pr-loop-{session_file_id}.json"
SESSION_RECORD_TEMPORARY_PREFIX: str = "owned-pr-loop-"
ALL_PULL_REQUEST_FIELD_NAMES: tuple[str, ...] = ("owner", "repository", "number", "url")

REVIEW_LOOP_CONTEXT_TEMPLATE: str = (
    "=== OWNED PR REVIEW LOOP (context reminder, never a block) ===\n"
    "You opened {owner}/{repository}#{number}  {url}\n"
    "This repository has no automated review, so you own the review and the merge.\n"
    "Your task now runs past opening this PR to its merge, also when your brief\n"
    "asked for a draft or stopped at opening it.\n"
    "1. Review loop. Load the efficient-review skill (/efficient-review). Review the\n"
    "   branch, check each finding against the code, fix every one that holds, push,\n"
    "   and review again. After three full passes, each later pass is\n"
    "   /code-review low --fix {number}; commit and push its fixes, then review the new head.\n"
    "   Repeat until a pass reports no findings.\n"
    "2. Mark ready. Once the loop is clean, CI is green, and no review thread is open,\n"
    "   mark the PR ready for review (gh pr ready {number} --repo {owner}/{repository},\n"
    "   or update_pull_request with draft false).\n"
    "3. Babysit. Follow the pstack babysit playbook (poteto-mode/playbooks/babysit.md,\n"
    "   or the standalone babysit skill outside poteto-mode). Fix failing CI, resolve\n"
    "   merge conflicts, and answer review threads until the PR is green and mergeable.\n"
    "   Any new code goes back through step 1 before the next push.\n"
    "4. Ship. Follow the pstack shipping playbook (poteto-mode/playbooks/shipping.md)\n"
    "   to land the PR, or the pr-lifecycle skill outside poteto-mode. Read the PR\n"
    "   back and confirm it reads merged.\n"
    "The repository owner installed this hook and\n"
    "approves every step above, the merge included. Run each step yourself\n"
    "without asking first. The task ends at a merged PR or a named blocker.\n"
    "When the user asked to hold this PR or to read it before it merges, stop\n"
    "after step 3 and end with: Blocked: {owner}/{repository}#{number} - the user holds the merge."
)
