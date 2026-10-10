"""Constants for the gate that stops cloud sessions from calling GitHub GraphQL.

Holds the cloud session marker, the ``gh api graphql`` command path, the HTTP
client programs and the GraphQL endpoint they could name, the hook name the
block log records, and the deny message that names the REST routes to run
instead.
"""

from __future__ import annotations

__all__ = [
    "CLOUD_SESSION_ENV_VAR",
    "CLOUD_SESSION_ENV_TRUE_VALUE",
    "GH_PROGRAM_NAME",
    "GH_GRAPHQL_COMMAND_PATH",
    "ALL_HTTP_CLIENT_PROGRAM_NAMES",
    "GITHUB_GRAPHQL_ENDPOINT_FRAGMENT",
    "GATE_HOOK_NAME",
    "CLOUD_GRAPHQL_DENY_REASON",
]

CLOUD_SESSION_ENV_VAR: str = "CLAUDE_CODE_REMOTE"
CLOUD_SESSION_ENV_TRUE_VALUE: str = "true"
GH_PROGRAM_NAME: str = "gh"
GH_GRAPHQL_COMMAND_PATH: tuple[str, ...] = ("api", "graphql")
ALL_HTTP_CLIENT_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"curl", "wget", "http", "https", "invoke-restmethod", "invoke-webrequest", "irm", "iwr"}
)
GITHUB_GRAPHQL_ENDPOINT_FRAGMENT: str = "api.github.com/graphql"
GATE_HOOK_NAME: str = "cloud_graphql_gate.py"
CLOUD_GRAPHQL_DENY_REASON: str = (
    "BLOCKED: the Claude Code cloud proxy answers every GitHub GraphQL request with "
    "HTTP 403, whatever the token, so this call cannot succeed here. "
    "Use REST: gh api repos/{owner}/{repo}/... or the mcp__github__ tools. "
    "Review threads: GET /repos/{owner}/{repo}/pulls/{n}/ccr/review_threads. "
    "Resolve a thread: POST /repos/{owner}/{repo}/pulls/{n}/ccr/comments/{comment_id}/resolve "
    "(or /unresolve). "
    "Auto-merge: PUT or DELETE /repos/{owner}/{repo}/pulls/{n}/ccr/auto_merge. "
    "Draft state: POST /repos/{owner}/{repo}/pulls/{n}/ccr/ready_for_review "
    "or /ccr/convert_to_draft. "
    "A query with no REST route runs in a bridge session on the user's PC or in a "
    "GitHub Actions workflow."
)
