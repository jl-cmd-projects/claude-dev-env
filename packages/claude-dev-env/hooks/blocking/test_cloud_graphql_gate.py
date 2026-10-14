"""Tests for cloud_graphql_gate, which stops cloud sessions from calling GitHub GraphQL."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

import cloud_graphql_gate as gate


def _stdout_from_main(payload: dict[str, object]) -> str:
    """Return what main() wrote to stdout for one hook payload."""
    captured_stdout = StringIO()
    with (
        patch("sys.stdin", StringIO(json.dumps(payload))),
        patch("sys.stdout", captured_stdout),
        patch.object(gate, "log_hook_block"),
    ):
        gate.main()
    return captured_stdout.getvalue()


@pytest.fixture
def cloud_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the hook process as running inside a Claude Code cloud session."""
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")


@pytest.mark.parametrize(
    "command",
    [
        "gh api graphql -f query='query{viewer{login}}'",
        "gh.exe api graphql -F owner=o -f query=@q.graphql",
        "cd repo && gh api graphql --paginate -f query=@q.graphql",
        'bash -c "gh api graphql -f query=@q.graphql"',
        "curl -sS -X POST https://api.github.com/graphql -d @q.json",
        "curl -H 'Authorization: Bearer x' HTTPS://API.GITHUB.COM/GRAPHQL",
        "wget --post-data=@q.json https://api.github.com/graphql",
        "Invoke-RestMethod -Method Post -Uri https://api.github.com/graphql -Body $q",
        "gh pr create --draft --title t --body-file b.md",
        "gh pr view 12 --json title",
        "gh pr checks 12",
        "gh issue list -L 1",
        "gh repo clone o/r",
        "gh repo view o/r",
        "gh label list",
        "gh search prs repo:o/r",
        "gh ruleset list",
        "gh gist list",
        "gh api -X POST graphql -f query='mutation{x}'",
        "gh api --method POST graphql -f query=@q.graphql",
        "gh api -H 'Accept: application/json' graphql -f query=@q",
        "gh api /graphql -f query=@q",
        "gh api https://api.github.com/graphql -f query=@q",
        "gh -R o/r pr list",
        "gh pr -R o/r list",
        "gh pr --repo o/r view 12",
        "gh pr merge 12 --body -h",
        "gh pr view 12 --web",
        "gh issue list --web",
        "gh project item-list 1 --owner o",
        "gh discussion list",
        "gh status",
        "gh status -o o",
        "gh org list",
        "gh repo archive o/r --yes",
        "gh repo unarchive o/r --yes",
        "curl -X POST https://api.github.com:443/graphql -d @q.json",
        "if gh pr view 12; then echo ok; fi",
        "if true; then gh api graphql -f query=@q; fi",
        "while gh pr list; do sleep 1; done",
        "! gh pr list",
        "command gh pr list",
        "exec gh issue list",
        'echo "$(gh pr list)"',
        "echo `gh pr view 12`",
        "PR_URL=$(gh pr create --title t --body-file b.md)",
        "(gh pr view 12)",
        "python3 -c \"import requests; requests.post('https://api.github.com/graphql')\"",
        "node -e \"fetch('https://api.github.com/graphql', {method: 'POST'})\"",
        "gh release list -L 1",
        "gh release view v1 --json name",
        "gh workflow run ci.yml",
        "gh workflow run ci.yml -f -r",
        "gh pr list --search -w",
        "echo \"$(printf ')'; gh pr list)\"",
        "x=`echo \\`gh pr list\\``",
        'echo $(echo "$(gh api graphql -f query=@q)")',
        "python3.12 -c \"u('https://api.github.com/graphql')\"",
        "pypy3 -c \"u('https://api.github.com/graphql')\"",
    ],
)
def test_should_detect_a_github_graphql_call(command: str) -> None:
    assert gate.calls_github_graphql(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/o/r/pulls/1/ccr/review_threads",
        "gh api user",
        "gh pr diff 12",
        "gh pr create --help",
        "gh issue view -h",
        "gh pr list -R o/r --help",
        "gh pr list --web",
        "gh pr list -w -R o/r",
        "gh project",
        "gh api repos/o/r/contents/docs/graphql.md",
        "gh api repos/o/r/issues -f title=graphql",
        "gh repo fork o/r",
        "gh repo rename new-name",
        "echo '$(gh pr list)'",
        "command -v gh",
        "gh pr view -w -h",
        "gh pr list --state open --web",
        "gh release view --json name",
        "gh workflow run ci.yml --ref main",
        "gh workflow run ci.yml -r main",
        "gh workflow run ci.yml --ref=main",
        "gh search repos claude-dev-env",
        "gh run view 12",
        "python3 scripts/review_closure.py o/r 1",
        "gh pr",
        "gh run list -L 1",
        "gh workflow list",
        "gh label create bug",
        "curl -sS https://api.github.com/repos/o/r",
        'grep -rn "api.github.com/graphql" scripts',
        'echo "gh api graphql"',
        'git commit -m "drop gh api graphql calls"',
    ],
)
def test_should_pass_rest_calls_and_text_that_only_mentions_graphql(command: str) -> None:
    assert gate.calls_github_graphql(command) is False


def test_should_deny_gh_api_graphql_in_a_cloud_session_and_name_the_rest_routes(
    cloud_session: None,
) -> None:
    decision = json.loads(
        _stdout_from_main(
            {"tool_name": "Bash", "tool_input": {"command": "gh api graphql -f query=@q"}}
        )
    )
    specific_output = decision["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    reason = specific_output["permissionDecisionReason"]
    assert "GET /repos/{owner}/{repo}/pulls/{n}/ccr/review_threads" in reason
    assert "gh api repos/{owner}/{repo}/..." in reason
    assert "mcp__github__create_pull_request" in reason


def test_should_deny_a_powershell_endpoint_call_in_a_cloud_session(cloud_session: None) -> None:
    command = "Invoke-RestMethod -Uri https://api.github.com/graphql -Method Post"
    decision = json.loads(
        _stdout_from_main({"tool_name": "PowerShell", "tool_input": {"command": command}})
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_should_stay_quiet_outside_a_cloud_session() -> None:
    assert (
        _stdout_from_main(
            {"tool_name": "Bash", "tool_input": {"command": "gh api graphql -f query=@q"}}
        )
        == ""
    )


def test_should_stay_quiet_for_a_rest_call_in_a_cloud_session(cloud_session: None) -> None:
    rest_command = "gh api repos/o/r/pulls/1/ccr/review_threads"
    assert _stdout_from_main({"tool_name": "Bash", "tool_input": {"command": rest_command}}) == ""


def test_should_stay_quiet_for_another_tool_in_a_cloud_session(cloud_session: None) -> None:
    assert (
        _stdout_from_main({"tool_name": "Write", "tool_input": {"command": "gh api graphql"}}) == ""
    )
