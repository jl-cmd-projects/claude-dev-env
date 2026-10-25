"""Tests for the scope-boundary session flags and stub check."""

import shutil
import subprocess
import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
for each_root in (
    flow_directory,
    flow_directory.parent / "features-start-with-an-eval",
):
    if str(each_root) not in sys.path:
        sys.path.insert(0, str(each_root))

from scope_eval_support.config.constants import (
    DECISION_TOOL_FULL_NAME,
    FAILURE_DECISION_STUB,
    UNREADABLE_DIFF_TEXT,
)
from scope_eval_support.workspace import (
    cases_digest,
    decision_stub_failure,
    prepare_workspace,
    scope_words,
    starting_commit,
    workspace_diff,
)

MCP_CONFIG_PATH = Path("decision-mcp.json")


def _init_event(status: str) -> dict[str, object]:
    return {
        "type": "system",
        "subtype": "init",
        "mcp_servers": [{"name": "thread", "status": status}],
    }


def test_scope_words_should_allow_the_decision_tool() -> None:
    assert DECISION_TOOL_FULL_NAME in scope_words(["claude", "-p"], MCP_CONFIG_PATH, "")


def test_scope_words_should_resume_the_setup_session_by_id() -> None:
    all_words = scope_words(["claude", "-p"], MCP_CONFIG_PATH, "setup-id")
    assert all_words[2:4] == ["--resume", "setup-id"]


def test_scope_words_should_not_resume_a_one_turn_case() -> None:
    assert "--resume" not in scope_words(["claude", "-p"], MCP_CONFIG_PATH, "")


def test_decision_stub_failure_should_pass_a_connected_stub() -> None:
    assert decision_stub_failure([_init_event("connected")]) is None


def test_decision_stub_failure_should_flag_a_stub_that_failed() -> None:
    assert decision_stub_failure([_init_event("failed")])[0] == FAILURE_DECISION_STUB


def test_decision_stub_failure_should_flag_a_stream_with_no_init_event() -> None:
    assert decision_stub_failure([]) == (FAILURE_DECISION_STUB, None)


def test_cases_digest_should_change_when_a_prompt_changes() -> None:
    first_case = {"id": "d01", "prompt": "Port it."}
    assert cases_digest([first_case]) != cases_digest(
        [{**first_case, "prompt": "Port it and lock it."}]
    )


def test_cases_digest_should_ignore_a_label_change() -> None:
    first_case = {"id": "d01", "prompt": "Port it.", "in_scope": "The port."}
    assert cases_digest([first_case]) == cases_digest(
        [{**first_case, "in_scope": "The port and its test."}]
    )


def _changed_workspace_diff(tmp_path: Path, should_commit: bool) -> str:
    workspace = prepare_workspace({})
    try:
        from_commit = starting_commit(workspace)
        (workspace / "added_by_session.txt").write_text("new line\n", encoding="utf-8")
        if should_commit:
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=t",
                    "-c",
                    "user.email=t@t",
                    "commit",
                    "-qm",
                    "x",
                ],
                cwd=workspace,
                check=True,
            )
        return workspace_diff(workspace, from_commit)
    finally:
        shutil.move(str(workspace), str(tmp_path / workspace.name))


def test_workspace_diff_should_show_a_file_the_session_added(tmp_path: Path) -> None:
    assert "+new line" in _changed_workspace_diff(tmp_path, should_commit=False)


def test_workspace_diff_should_show_a_change_the_session_committed(
    tmp_path: Path,
) -> None:
    assert "added_by_session.txt" in _changed_workspace_diff(
        tmp_path, should_commit=True
    )


def test_workspace_diff_should_return_a_note_when_git_is_gone(tmp_path: Path) -> None:
    assert workspace_diff(tmp_path, "0" * 40) == UNREADABLE_DIFF_TEXT
