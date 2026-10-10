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
    ],
)
def test_should_detect_a_github_graphql_call(command: str) -> None:
    assert gate.calls_github_graphql(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/o/r/pulls/1/ccr/review_threads",
        "gh api user",
        "gh pr view 12",
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


@pytest.mark.parametrize("marker_value", ["TRUE", " true "])
def test_should_read_the_cloud_marker_case_and_space_blind(
    monkeypatch: pytest.MonkeyPatch, marker_value: str
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", marker_value)
    assert gate.is_cloud_session() is True


def test_should_not_treat_a_false_marker_as_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    assert gate.is_cloud_session() is False
