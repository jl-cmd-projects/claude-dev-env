"""Constants for the gate that stops cloud sessions from calling GitHub GraphQL.

Holds the ``gh`` commands that call GraphQL, the ``gh`` subcommands inside
those groups that call REST, the ``gh`` options read while finding the command
words, the help flags that reach no network, the browser-only forms, the HTTP
client programs and the GraphQL endpoint pattern they could name, the hook name
the block log records, and the deny message that names the REST routes to run
instead.
"""

from __future__ import annotations

import re

__all__ = [
    "GH_PROGRAM_NAME",
    "GH_API_SUBCOMMAND",
    "GH_GRAPHQL_ENDPOINT",
    "GH_ENDPOINT_PATH_SEPARATOR",
    "GH_OPTION_PREFIX",
    "GH_COMMAND_PATH_LENGTH",
    "ALL_GH_GRAPHQL_COMMAND_GROUPS",
    "ALL_GH_REST_COMMAND_PATHS_IN_GRAPHQL_GROUPS",
    "ALL_GH_GRAPHQL_COMMAND_PATHS",
    "ALL_GH_REPOSITORY_OPTIONS",
    "ALL_GH_HELP_FLAGS",
    "ALL_GH_WEB_FLAGS",
    "ALL_GH_BROWSER_ONLY_COMMAND_PATHS",
    "ALL_HTTP_CLIENT_PROGRAM_NAMES",
    "GITHUB_GRAPHQL_ENDPOINT_PATTERN",
    "GATE_HOOK_NAME",
    "CLOUD_GRAPHQL_DENY_REASON",
]

GH_PROGRAM_NAME: str = "gh"
GH_API_SUBCOMMAND: str = "api"
GH_GRAPHQL_ENDPOINT: str = "graphql"
GH_ENDPOINT_PATH_SEPARATOR: str = "/"
GH_OPTION_PREFIX: str = "-"
GH_COMMAND_PATH_LENGTH: int = 2
ALL_GH_GRAPHQL_COMMAND_GROUPS: frozenset[str] = frozenset({"pr", "issue", "project", "discussion"})
ALL_GH_REST_COMMAND_PATHS_IN_GRAPHQL_GROUPS: frozenset[tuple[str, ...]] = frozenset(
    {("pr", "diff")}
)
ALL_GH_GRAPHQL_COMMAND_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("status",),
        ("org", "list"),
        ("repo", "view"),
        ("repo", "clone"),
        ("repo", "list"),
        ("repo", "archive"),
        ("repo", "unarchive"),
        ("label", "list"),
        ("search", "prs"),
        ("search", "issues"),
        ("ruleset", "list"),
        ("gist", "list"),
    }
)
ALL_GH_REPOSITORY_OPTIONS: frozenset[str] = frozenset({"-R", "--repo"})
ALL_GH_HELP_FLAGS: frozenset[str] = frozenset({"--help", "-h"})
ALL_GH_WEB_FLAGS: frozenset[str] = frozenset({"--web", "-w"})
ALL_GH_BROWSER_ONLY_COMMAND_PATHS: frozenset[tuple[str, ...]] = frozenset({("pr", "list")})
ALL_HTTP_CLIENT_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"curl", "wget", "http", "https", "invoke-restmethod", "invoke-webrequest", "irm", "iwr"}
)
GITHUB_GRAPHQL_ENDPOINT_PATTERN: re.Pattern[str] = re.compile(
    r"api\.github\.com(?::\d+)?/graphql", re.IGNORECASE
)
GATE_HOOK_NAME: str = "cloud_graphql_gate.py"
CLOUD_GRAPHQL_DENY_REASON: str = (
    "BLOCKED: the Claude Code cloud proxy answers every GitHub GraphQL request with "
    "HTTP 403, whatever the token. gh api graphql calls it, and so do gh pr and gh issue "
    "(all but gh pr diff and gh pr list --web), gh project, gh discussion, gh status, "
    "gh org list, gh repo view/clone/list/archive/unarchive, gh label list, "
    "gh search prs/issues, gh ruleset list, and gh gist list. "
    "Use REST through gh api repos/{owner}/{repo}/... or the mcp__github__ tools. "
    "Open a PR: mcp__github__create_pull_request, or gh api repos/{owner}/{repo}/pulls "
    "--input pr.json with title, head, base, body and draft in the JSON. "
    "Read a PR: gh api repos/{owner}/{repo}/pulls/{n}. "
    "Checks: gh api repos/{owner}/{repo}/commits/{sha}/check-runs. "
    "Issues: gh api repos/{owner}/{repo}/issues/{n}. "
    "Clone: git clone https://github.com/{owner}/{repo}. "
    "Review threads: GET /repos/{owner}/{repo}/pulls/{n}/ccr/review_threads. "
    "Resolve a thread: POST /repos/{owner}/{repo}/pulls/{n}/ccr/comments/{comment_id}/resolve "
    "(or /unresolve). "
    "Auto-merge: PUT or DELETE /repos/{owner}/{repo}/pulls/{n}/ccr/auto_merge. "
    "Draft state: POST /repos/{owner}/{repo}/pulls/{n}/ccr/ready_for_review "
    "or /ccr/convert_to_draft. "
    "A query with no REST route runs in a bridge session on the user's PC or in a "
    "GitHub Actions workflow."
)
