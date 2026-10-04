"""Behavior tests for the proof-in-practice check on a new pull request."""

import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pull_request_proof as gate
from hooks_constants.pull_request_proof_constants import MISSING_BODY_REASON, MISSING_PROOF_REASON

PROVEN_BODY = "## Summary\nAdds a gate.\n\n## Proof in practice\nRan `python run.py`.\n> denied\n"
UNPROVEN_BODY = "## Summary\nAdds a gate.\n\n## Verification\nUnit tests pass.\n"


def _shell(command: str, working_directory: Path | None = None) -> dict[str, object]:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(working_directory or ""),
    }


def _mcp_create(body: object) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "o", "repo": "r", "title": "t", "body": body},
    }


def test_proof_section_should_stop_at_a_heading_of_the_same_level() -> None:
    body = "### Proof in practice\nran `a`\n#### Child\nkept\n### Local checks\ndropped"
    assert gate.proof_section(body) == "ran `a`\n#### Child\nkept"


def test_proof_section_should_return_none_without_the_heading() -> None:
    assert gate.proof_section(UNPROVEN_BODY) is None


def test_mcp_create_without_proof_should_be_denied() -> None:
    assert gate.missing_proof_reason(_mcp_create(UNPROVEN_BODY)) == MISSING_PROOF_REASON


def test_mcp_create_with_no_body_should_be_denied() -> None:
    assert gate.missing_proof_reason(_mcp_create(None)) == MISSING_PROOF_REASON


def test_mcp_create_with_proof_should_pass() -> None:
    assert gate.missing_proof_reason(_mcp_create(PROVEN_BODY)) is None


def test_heading_with_no_command_should_be_denied() -> None:
    body = "## Proof in practice\nIt works.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == MISSING_PROOF_REASON


def test_gh_create_body_file_with_proof_should_pass(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(PROVEN_BODY, encoding="utf-8")
    payload = _shell("gh pr create --draft --body-file body.md", tmp_path)
    assert gate.missing_proof_reason(payload) is None


def test_gh_create_body_file_without_proof_should_be_denied(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(UNPROVEN_BODY, encoding="utf-8")
    payload = _shell("gh pr create -F body.md", tmp_path)
    assert gate.missing_proof_reason(payload) == MISSING_PROOF_REASON


def test_gh_create_with_fill_should_ask_for_a_body() -> None:
    assert gate.missing_proof_reason(_shell("gh pr create --fill")) == MISSING_BODY_REASON


def test_wrapped_gh_create_should_be_read() -> None:
    payload = _shell("bash -c 'gh pr create --body \"no proof\"'")
    assert gate.missing_proof_reason(payload) == MISSING_PROOF_REASON


def test_pull_request_script_create_should_be_read(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(UNPROVEN_BODY, encoding="utf-8")
    payload = _shell("python3 scripts/pull_request.py create --body-file body.md", tmp_path)
    assert gate.missing_proof_reason(payload) == MISSING_PROOF_REASON


def test_other_pull_request_commands_should_pass() -> None:
    for each_command in ("gh pr edit 3 --body x", "git push -u origin b", "gh pr view"):
        assert gate.missing_proof_reason(_shell(each_command)) is None


def test_other_tools_should_pass() -> None:
    payload = {"tool_name": "mcp__github__update_pull_request", "tool_input": {"body": "x"}}
    assert gate.missing_proof_reason(payload) is None
