"""Behavior tests for the proof-in-practice and existing-work checks on a new pull request."""

import subprocess
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pull_request_proof as gate
from hooks_constants.pull_request_proof_constants import (
    MISSING_BODY_REASON,
    MISSING_EXISTING_WORK_REASON,
    MISSING_PROOF_REASON,
    UNREADABLE_CHANGES_REASON,
)

PROVEN_BODY = "## Summary\nAdds a gate.\n\n## Proof in practice\nRan `python run.py`.\n> denied\n"
UNPROVEN_BODY = "## Summary\nAdds a gate.\n\n## Verification\nUnit tests pass.\n"
SEARCHED_BODY = (
    "## Summary\nAdds a gate.\n\n## Existing work\n`gate.py:12` runs the check; this adds a flag.\n\n"
    "## Proof in practice\nRan `python run.py`.\n"
)
EMPTY_EXISTING_WORK_BODY = "## Existing work\n\n## Proof in practice\nRan `python run.py`.\n"


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


def test_existing_work_section_should_stop_at_a_heading_of_the_same_level() -> None:
    assert gate.section_under_existing_work(SEARCHED_BODY) == "`gate.py:12` runs the check; this adds a flag."


def test_mcp_create_without_existing_work_should_be_denied() -> None:
    assert gate.missing_existing_work_reason(_mcp_create(PROVEN_BODY)) == MISSING_EXISTING_WORK_REASON


def test_mcp_create_with_an_empty_existing_work_section_should_be_denied() -> None:
    payload = _mcp_create(EMPTY_EXISTING_WORK_BODY)
    assert gate.missing_existing_work_reason(payload) == MISSING_EXISTING_WORK_REASON


def test_mcp_create_with_existing_work_should_pass() -> None:
    assert gate.missing_existing_work_reason(_mcp_create(SEARCHED_BODY)) is None


def test_gh_create_body_file_without_existing_work_should_be_denied(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(PROVEN_BODY, encoding="utf-8")
    payload = _shell("gh pr create --draft --body-file body.md", tmp_path)
    assert gate.missing_existing_work_reason(payload) == MISSING_EXISTING_WORK_REASON


def test_unreadable_body_should_leave_the_deny_to_the_proof_check() -> None:
    payload = _shell("gh pr create --fill")
    assert gate.missing_existing_work_reason(payload) is None
    assert gate.missing_proof_reason(payload) == MISSING_BODY_REASON


def test_other_pull_request_commands_should_pass_the_existing_work_check() -> None:
    for each_command in ("gh pr edit 3 --body x", "git push -u origin b", "gh pr view"):
        assert gate.missing_existing_work_reason(_shell(each_command)) is None


def _repository_with_change(tmp_path: Path, changed_file_name: str) -> Path:
    origin_path = tmp_path / "origin"
    clone_path = tmp_path / "clone"
    git_identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin_path)], check=True)
    (origin_path / "readme.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(origin_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(origin_path), *git_identity, "commit", "-q", "-m", "base"], check=True)
    subprocess.run(["git", "clone", "-q", str(origin_path), str(clone_path)], check=True)
    subprocess.run(["git", "-C", str(clone_path), "checkout", "-q", "-b", "feature"], check=True)
    (clone_path / changed_file_name).write_text("<p>x</p>\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(clone_path), *git_identity, "commit", "-q", "-m", "change"], check=True)
    return clone_path


def _mcp_create_on_branch(body: str, working_directory: Path) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"body": body, "head": "feature"},
        "cwd": str(working_directory),
    }


def test_should_deny_a_page_change_whose_proof_shows_no_picture(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "page.html")
    reason = gate.missing_look_reason(_mcp_create_on_branch(PROVEN_BODY, clone_path))
    assert reason is not None
    assert "page.html" in reason


def test_should_allow_a_page_change_whose_proof_links_a_screenshot(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "page.html")
    body = PROVEN_BODY + "![after](https://example.com/after.png)\n"
    assert gate.missing_look_reason(_mcp_create_on_branch(body, clone_path)) is None


def test_should_allow_a_python_only_change_without_a_picture(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "tool.py")
    assert gate.missing_look_reason(_mcp_create_on_branch(PROVEN_BODY, clone_path)) is None


def test_visible_changed_files_skips_a_different_head_branch(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "page.html")
    assert gate.visible_changed_files(str(clone_path), "feature") == ["page.html"]
    assert gate.visible_changed_files(str(clone_path), "other-branch") is None


def test_should_deny_when_git_cannot_read_the_branch_and_proof_shows_no_picture(tmp_path: Path) -> None:
    payload = _mcp_create_on_branch(PROVEN_BODY, tmp_path)
    assert gate.missing_look_reason(payload) == UNREADABLE_CHANGES_REASON


def test_visible_changed_files_falls_back_to_origin_main_without_origin_head(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "page.html")
    subprocess.run(["git", "-C", str(clone_path), "remote", "set-head", "origin", "-d"], check=True)
    subprocess.run(["git", "-C", str(clone_path), "checkout", "-q", "main"], check=True)
    assert gate.visible_changed_files(str(clone_path), "feature") == ["page.html"]


def test_should_read_the_head_flag_of_a_shell_create(tmp_path: Path) -> None:
    clone_path = _repository_with_change(tmp_path, "page.html")
    subprocess.run(["git", "-C", str(clone_path), "checkout", "-q", "main"], check=True)
    body_path = clone_path / "body.md"
    body_path.write_text(PROVEN_BODY, encoding="utf-8")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": f"gh pr create --head feature --title t --body-file {body_path}"},
        "cwd": str(clone_path),
    }
    reason = gate.missing_look_reason(payload)
    assert reason is not None
    assert "page.html" in reason
