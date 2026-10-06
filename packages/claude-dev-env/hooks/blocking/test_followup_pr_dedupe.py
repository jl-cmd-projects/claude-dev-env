"""Behavior tests for the one-follow-up-pull-request-per-parent check."""

import sys
from collections.abc import Mapping
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import followup_pr_dedupe as dedupe

OPEN_FOLLOWUP = {
    "number": 1769,
    "html_url": "https://github.com/jl-cmd/claude-dev-env/pull/1769",
    "body": "Follow-up to #1731. Fixes one smell.",
}
OTHER_FOLLOWUP = {
    "number": 1777,
    "html_url": "https://github.com/jl-cmd/claude-dev-env/pull/1777",
    "body": "follow-up to #17",
}


def _reader(all_open: list[Mapping[str, object]]) -> dedupe.OpenPullRequestReader:
    def read(owner: str, repo: str) -> list[Mapping[str, object]]:
        assert (owner, repo) == ("jl-cmd", "claude-dev-env")
        return all_open

    return read


def _failing_reader(*_all_reader_arguments: str) -> list[Mapping[str, object]]:
    raise OSError("network down")


def _mcp_payload(body: str) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "jl-cmd", "repo": "claude-dev-env", "body": body},
    }


def test_second_followup_for_one_parent_is_denied() -> None:
    reason = dedupe.duplicate_followup_reason(
        _mcp_payload("FOLLOW-UP TO #1731: another smell"), _reader([OTHER_FOLLOWUP, OPEN_FOLLOWUP])
    )
    assert reason is not None
    assert "#1769" in reason
    assert "Add this finding to the open follow-up pull request #1769" in reason


def test_first_followup_passes() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _reader([OTHER_FOLLOWUP])) is None


def test_parent_prefix_number_does_not_match_longer_parent() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #173"), _reader([OPEN_FOLLOWUP])) is None


def test_non_followup_pull_request_skips_the_read() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Adds a hook."), _failing_reader) is None


def test_read_failure_fails_open() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _failing_reader) is None


def test_gh_pr_create_inline_body_is_denied() -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create -R jl-cmd/claude-dev-env --title t --body 'Follow-up to #1731'"},
    }
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason is not None and "pull request #1769" in reason


def test_powershell_body_file_is_denied(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("Follow-up to #1731\n", encoding="utf-8")
    payload = {
        "tool_name": "PowerShell",
        "cwd": str(tmp_path),
        "tool_input": {"command": "gh pr create --repo jl-cmd/claude-dev-env --body-file body.md"},
    }
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason is not None and "pull request #1769" in reason


def test_body_from_arguments_reads_inline_text_and_body_files(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("From the file.", encoding="utf-8")
    assert dedupe.body_from_arguments(["--body", "Inline."], "") == "Inline."
    assert dedupe.body_from_arguments(["--body-file", "body.md"], str(tmp_path)) == "From the file."
    assert dedupe.body_from_arguments(["--body-file", "-"], str(tmp_path)) is None
    assert dedupe.body_from_arguments(["--fill"], str(tmp_path)) is None
