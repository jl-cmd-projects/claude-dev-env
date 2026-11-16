"""Behavior tests for the size check on a new pull request."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import gate_run_reads
from blocking import oversized_change as size
from blocking import pull_request_proof as proof
from hooks_constants.oversized_change_constants import OVERSIZED_PULL_REQUEST_REASON

GIT_IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
PLAIN_BODY = "## What this does\nAdds a tool.\n"
ONE_PULL_REQUEST_BODY = (
    PLAIN_BODY + "\n### Why one pull request\nThe schema and its reader must land together.\n"
)
EMPTY_ONE_PULL_REQUEST_BODY = PLAIN_BODY + "\n## Why one pull request\n\n## Risk\nLow.\n"


def _git(repository_path: Path, *all_arguments: str) -> None:
    subprocess.run(["git", "-C", str(repository_path), *GIT_IDENTITY, *all_arguments], check=True)


def _commit_lines(repository_path: Path, file_name: str, line_count: int) -> None:
    (repository_path / file_name).write_text(
        "".join(f"line {i}\n" for i in range(line_count)), encoding="utf-8"
    )
    _git(repository_path, "add", ".")
    _git(repository_path, "commit", "-q", "-m", f"add {file_name}")


def _clone_on_branch(tmp_path: Path, branch_name: str) -> Path:
    origin_path = tmp_path / "origin"
    clone_path = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin_path)], check=True)
    _commit_lines(origin_path, "README.md", 3)
    subprocess.run(["git", "clone", "-q", str(origin_path), str(clone_path)], check=True)
    _git(clone_path, "checkout", "-q", "-b", branch_name)
    return clone_path


def _create(clone_path: Path, body: str, extra_flags: str = "") -> dict[str, object]:
    (clone_path.parent / "body.md").write_text(body, encoding="utf-8")
    return {
        "tool_name": "Bash",
        "tool_input": {
            "command": f"gh pr create --title t --body-file ../body.md {extra_flags}".strip()
        },
        "cwd": str(clone_path),
    }


@pytest.fixture
def large_branch(tmp_path: Path) -> Path:
    clone_path = _clone_on_branch(tmp_path, "feature")
    _commit_lines(clone_path, "tool.py", 1500)
    return clone_path


def test_should_deny_a_create_over_the_bar_with_no_reason_section(large_branch: Path) -> None:
    reason = size.oversized_pull_request_reason(_create(large_branch, PLAIN_BODY))
    assert reason == OVERSIZED_PULL_REQUEST_REASON.format(
        measured_line_count=1500, measured_line_bar=1000
    )


def test_should_pass_a_create_over_the_bar_whose_body_says_why_it_stays_one(
    large_branch: Path,
) -> None:
    assert size.oversized_pull_request_reason(_create(large_branch, ONE_PULL_REQUEST_BODY)) is None


def test_should_deny_when_the_reason_section_is_empty(large_branch: Path) -> None:
    reason = size.oversized_pull_request_reason(_create(large_branch, EMPTY_ONE_PULL_REQUEST_BODY))
    assert reason == OVERSIZED_PULL_REQUEST_REASON.format(
        measured_line_count=1500, measured_line_bar=1000
    )


def test_should_pass_a_create_under_the_bar(tmp_path: Path) -> None:
    clone_path = _clone_on_branch(tmp_path, "feature")
    _commit_lines(clone_path, "tool.py", 900)
    assert size.oversized_pull_request_reason(_create(clone_path, PLAIN_BODY)) is None


def test_should_count_a_stacked_level_against_its_own_base(tmp_path: Path) -> None:
    clone_path = _clone_on_branch(tmp_path, "parent")
    _commit_lines(clone_path, "library.py", 1500)
    _git(clone_path, "push", "-q", "origin", "parent")
    _git(clone_path, "checkout", "-q", "-b", "child")
    _commit_lines(clone_path, "caller.py", 200)
    assert (
        size.oversized_pull_request_reason(_create(clone_path, PLAIN_BODY, "--base parent")) is None
    )
    assert size.local_measured_line_count(str(clone_path), "parent", None) == 200
    assert (
        size.oversized_pull_request_reason(_create(clone_path, PLAIN_BODY, "--base main"))
        is not None
    )


def test_should_leave_out_linguist_generated_files_and_lockfiles(tmp_path: Path) -> None:
    clone_path = _clone_on_branch(tmp_path, "feature")
    (clone_path / ".gitattributes").write_text(
        "schema/*.json linguist-generated\n", encoding="utf-8"
    )
    (clone_path / "schema").mkdir()
    _commit_lines(clone_path, "schema/types.json", 3000)
    _commit_lines(clone_path, "uv.lock", 2000)
    _commit_lines(clone_path, "tool.py", 40)
    assert size.local_measured_line_count(str(clone_path), None, None) == 41
    assert size.oversized_pull_request_reason(_create(clone_path, PLAIN_BODY)) is None


def test_should_count_only_the_edited_lines_of_a_rename(large_branch: Path) -> None:
    _git(large_branch, "push", "-q", "origin", "feature")
    _git(large_branch, "checkout", "-q", "-b", "move")
    _git(large_branch, "mv", "tool.py", "moved_tool.py")
    _git(large_branch, "commit", "-q", "-m", "move")
    assert size.local_measured_line_count(str(large_branch), "feature", None) == 0


def test_should_pass_a_body_edit(large_branch: Path) -> None:
    (large_branch.parent / "body.md").write_text(PLAIN_BODY, encoding="utf-8")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr edit 7 --body-file ../body.md"},
        "cwd": str(large_branch),
    }
    assert size.oversized_pull_request_reason(payload) is None


def test_should_pass_when_no_base_can_be_resolved(large_branch: Path) -> None:
    assert size.local_measured_line_count(str(large_branch), "no-such-branch", None) is None
    assert (
        size.oversized_pull_request_reason(
            _create(large_branch, PLAIN_BODY, "--base no-such-branch")
        )
        is None
    )


def test_remote_count_should_sum_files_and_leave_out_lockfiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_compare_lines = [
        "2",
        json.dumps(["tool.py", 1100, 100]),
        json.dumps(["web/package-lock.json", 900, 0]),
    ]
    monkeypatch.setattr(size, "_compare_lines", lambda *all_arguments: all_compare_lines)
    assert size.remote_measured_line_count("o/r", "main", "feature") == 1200


def test_remote_count_should_be_unknown_at_the_compare_file_cap_under_the_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        size, "_compare_lines", lambda *all_arguments: ["300", json.dumps(["a.py", 500, 0])]
    )
    assert size.remote_measured_line_count("o/r", "main", "feature") is None


def test_remote_count_should_return_the_listed_lines_at_the_file_cap_when_they_pass_the_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        size, "_compare_lines", lambda *all_arguments: ["300", json.dumps(["a.py", 5000, 0])]
    )
    assert size.remote_measured_line_count("o/r", "main", "feature") == 5000


def _generated_schema_branch(tmp_path: Path) -> Path:
    clone_path = _clone_on_branch(tmp_path, "feature")
    (clone_path / ".gitattributes").write_text(
        "schema/*.json linguist-generated\n", encoding="utf-8"
    )
    (clone_path / "schema").mkdir()
    (clone_path / "sub").mkdir()
    _commit_lines(clone_path, "schema/types.json", 3000)
    _commit_lines(clone_path, "sub/tool.py", 40)
    return clone_path


def test_should_leave_out_generated_files_when_the_session_sits_in_a_subdirectory(
    tmp_path: Path,
) -> None:
    clone_path = _generated_schema_branch(tmp_path)
    assert size.local_measured_line_count(str(clone_path), None, None) == 41
    assert size.local_measured_line_count(str(clone_path / "sub"), None, None) == 41


def test_should_read_attributes_of_a_path_list_longer_than_the_argument_limit(
    tmp_path: Path,
) -> None:
    clone_path = _clone_on_branch(tmp_path, "feature")
    deep_directory = Path(*["d" * 200] * 15)
    (clone_path / deep_directory).mkdir(parents=True)
    (clone_path / ".gitattributes").write_text("*.json linguist-generated\n", encoding="utf-8")
    for each_index in range(700):
        (clone_path / deep_directory / f"{each_index:04d}{'n' * 150}.json").write_text(
            "x\n", encoding="utf-8"
        )
    _commit_lines(clone_path, "tool.py", 40)
    assert size.local_measured_line_count(str(clone_path), None, None) == 41


def test_should_ask_git_for_the_head_once_when_the_proof_check_already_did(
    large_branch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_started_commands: list[list[str]] = []
    start_child = gate_run_reads.started_child

    def recording_start(all_command_words: list[str], *all_arguments: object) -> object:
        all_started_commands.append(list(all_command_words))
        return start_child(all_command_words, *all_arguments)

    monkeypatch.setattr(gate_run_reads, "started_child", recording_start)
    with gate_run_reads.gate_run():
        assert proof.visible_changed_files(str(large_branch), "feature") == []
        assert size.local_measured_line_count(str(large_branch), None, "feature") == 1500
    assert sum("--show-current" in each_command for each_command in all_started_commands) == 1
