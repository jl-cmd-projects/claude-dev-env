"""Behavior tests for the proof-in-practice, existing-work and eval checks on a new pull request."""

import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pull_request_proof as gate
from hooks_constants.pull_request_proof_constants import (
    COMPARE_FILE_LIST_LIMIT,
    MISSING_BODY_REASON,
    MISSING_EVAL_SECTION_REASON,
    MISSING_EXISTING_WORK_REASON,
    MISSING_PROOF_REASON,
    TEST_ONLY_PROOF_REASON,
    UNPROVEN_PROOF_REASON,
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


def test_proof_whose_only_command_is_a_test_run_should_be_denied() -> None:
    body = "## Proof in practice\nRan `pytest tests/test_x.py`.\n> 4 passed\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_test_run_and_a_live_command_should_pass() -> None:
    body = "## Proof in practice\nRan `pytest tests/test_x.py` and `python run.py --input a.txt`.\n> denied\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_only_a_live_command_should_pass() -> None:
    body = "## Proof in practice\nRan `python run.py --input a.txt`.\n> denied\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_several_test_runners_should_be_denied() -> None:
    body = (
        "## Proof in practice\n`python -m pytest -q`, `python3 -m unittest discover`,"
        " `uv run pytest`, `npm test`, `npx vitest run`, `jest`, `go test ./...`, `cargo test`\n"
    )
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_test_run_and_file_references_should_be_denied() -> None:
    body = "## Proof in practice\nRan `pytest tests/x.py` against `gate.py:12` and `src/x.py`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_that_says_its_target_run_is_not_proven_should_be_denied() -> None:
    body = (
        "## Proof in practice\nRan `python verify.py theme`.\n> PASS\n\n"
        "Not proven here: a fresh Convert run of Bear Penguin that rewrites the record.\n"
    )
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(
        admission="Not proven here: a fresh Convert run of Bear Penguin that rewrites the record."
    )


@pytest.mark.parametrize(
    "admission", ["unproven", "not yet tested", "Untested", "unverified", "not verified", "not been tested", "not fully verified"]
)
def test_each_unproven_marker_in_proof_prose_should_be_denied(admission: str) -> None:
    admission_line = f"The live dialer path is {admission}."
    body = f"## Proof in practice\nRan `python run.py`.\n{admission_line}\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(admission=admission_line)


def test_unproven_line_moved_under_a_not_covered_heading_should_pass() -> None:
    body = (
        "## Proof in practice\nRan `python run.py`.\n> PASS\n\n"
        "## Not covered\n\nNot proven here: a run on an older session.\n"
    )
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_unproven_words_inside_quoted_output_should_pass() -> None:
    body = (
        "## Proof in practice\nRan `python run.py`, which printed `unverified sender denied`.\n"
        "```\n$ python run.py\nstatus: not proven\n```\n"
    )
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_unproven_admission_after_a_one_line_triple_backtick_span_should_be_denied() -> None:
    body = (
        "## Proof in practice\nRan `python run.py`.\n```python run.py``` -> PASS\n"
        "Not proven here: the live run on the target.\n"
    )
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(
        admission="Not proven here: the live run on the target."
    )


def test_test_run_after_a_one_line_triple_backtick_span_should_be_denied() -> None:
    body = "## Proof in practice\n```pytest``` ok\nRan `pytest tests/`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_unproven_words_in_a_fence_inside_a_blockquote_should_pass() -> None:
    body = "## Proof in practice\nRan `python run.py`.\n> ```\n> status: not proven\n> ```\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_unproven_words_in_a_tilde_fence_should_pass() -> None:
    body = "## Proof in practice\nRan `python run.py`.\n~~~\nstatus: not proven\n~~~\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_tilde_line_inside_a_backtick_fence_keeps_the_fence_open() -> None:
    body = "## Proof in practice\nRan `python run.py`.\n```\n~~~\nstatus: not proven\n```\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_admission_after_a_backtick_fence_holding_a_tilde_line_should_be_denied() -> None:
    body = "## Proof in practice\nRan `python run.py`.\n```\n~~~\n```\nNot proven here: the live run.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(
        admission="Not proven here: the live run."
    )


def test_unproven_deny_quotes_the_line_as_written() -> None:
    body = "## Proof in practice\nRan `python run.py`.\nNot proven here: the `convert.py` run on the target.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(
        admission="Not proven here: the `convert.py` run on the target."
    )


def test_unproven_admission_inside_a_blockquote_should_be_denied() -> None:
    body = "## Proof in practice\nRan `python run.py`.\n> Not proven here: the live dialer run.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == UNPROVEN_PROOF_REASON.format(
        admission="> Not proven here: the live dialer run."
    )


def test_proof_with_a_test_run_piped_into_tee_should_be_denied() -> None:
    body = "## Proof in practice\nRan `pytest x | tee log`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_test_run_piped_into_tail_should_be_denied() -> None:
    body = "## Proof in practice\nRan `pytest x 2>&1 | tail -5`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_live_script_piped_into_tail_should_pass() -> None:
    body = "## Proof in practice\nRan `pytest x` and `./run.sh --input a.txt | tail -5`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_a_fenced_live_command_beside_a_test_run_should_pass() -> None:
    body = "## Proof in practice\nRan `pytest`.\n```\n$ python run.py\ndenied\n```\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_only_a_fenced_test_run_should_be_denied() -> None:
    body = "## Proof in practice\n```\n$ npm test\n12 passing\n```\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_gh_create_body_file_with_test_only_proof_should_be_denied(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("## Proof in practice\nRan `go test ./...`.\n", encoding="utf-8")
    payload = _shell("gh pr create --draft --body-file body.md", tmp_path)
    assert gate.missing_proof_reason(payload) == TEST_ONLY_PROOF_REASON


def test_proof_with_only_py_test_should_be_denied() -> None:
    body = "## Proof in practice\nRan `py.test`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_only_a_fenced_pytest_exe_should_be_denied() -> None:
    body = "## Proof in practice\n```\n$ pytest.exe\n```\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_only_a_source_citation_should_pass() -> None:
    body = "## Proof in practice\nSee `src/x.py`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_unittest_after_an_interpreter_flag_should_be_denied() -> None:
    body = "## Proof in practice\nRan `python -q -m unittest discover`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_unittest_after_a_valued_interpreter_flag_should_be_denied() -> None:
    body = "## Proof in practice\nRan `python -W default -m unittest`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_script_that_mentions_unittest_should_pass() -> None:
    body = "## Proof in practice\nRan `python script.py -m unittest`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_a_module_other_than_unittest_should_pass() -> None:
    body = "## Proof in practice\nRan `python -W default -m my_app`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


def test_proof_with_a_quoted_test_runner_word_should_be_denied() -> None:
    body = "## Proof in practice\nRan `npm \"test\"` and `cargo \"test\"`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_a_quoted_unittest_module_should_be_denied() -> None:
    body = "## Proof in practice\nRan `python -m \"unittest\"`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_coverage_running_unittest_should_be_denied() -> None:
    body = "## Proof in practice\nRan `coverage run -m unittest discover`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) == TEST_ONLY_PROOF_REASON


def test_proof_with_coverage_running_an_application_should_pass() -> None:
    body = "## Proof in practice\nRan `coverage run -m my_app`.\n"
    assert gate.missing_proof_reason(_mcp_create(body)) is None


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


def _fake_gh_api(all_responses: dict[str, list[str] | None], all_endpoints: list[str]):
    def fake_gh_api_lines(endpoint: str, query: str) -> list[str] | None:
        all_endpoints.append(endpoint)
        return all_responses.get(endpoint)

    return fake_gh_api_lines


def _shell_create_elsewhere(tmp_path: Path, extra_flags: str) -> dict[str, object]:
    body_path = tmp_path / "body.md"
    body_path.write_text(PROVEN_BODY, encoding="utf-8")
    return _shell(f"gh pr create --title t --body-file {body_path} {extra_flags}", tmp_path)


def test_should_allow_a_python_only_change_the_compare_api_lists_when_git_cannot_read_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({compare_endpoint: ["tool.py"]}, all_endpoints))
    payload = _shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature")
    assert gate.missing_look_reason(payload) is None
    assert all_endpoints == [compare_endpoint]


def test_should_deny_a_page_change_the_compare_api_lists_without_a_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_responses = {"repos/o/r": ["trunk"], "repos/o/r/compare/trunk...feature": ["web/page.html", "tool.py"]}
    all_endpoints: list[str] = []
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api(all_responses, all_endpoints))
    reason = gate.missing_look_reason(_shell_create_elsewhere(tmp_path, "-R o/r --head=feature"))
    assert reason is not None
    assert "web/page.html" in reason
    assert "tool.py" not in reason
    assert all_endpoints == ["repos/o/r", "repos/o/r/compare/trunk...feature"]


def test_should_deny_as_unreadable_when_the_compare_api_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({}, []))
    payload = _shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature")
    reason = gate.missing_look_reason(payload)
    assert reason == UNREADABLE_CHANGES_REASON
    assert reason is not None
    assert "compare API" in reason
    assert "--repo" in reason
    assert "--head" in reason
    assert "origin fetched" in reason
    assert "Artifact" in reason
    assert "before any change to this gate" in reason


def _python_paths(count: int) -> list[str]:
    return [f"pkg/module_{each_index}.py" for each_index in range(count)]


def test_should_deny_as_unreadable_when_a_full_compare_page_lists_no_visible_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    monkeypatch.setattr(
        gate,
        "_gh_api_lines",
        _fake_gh_api({compare_endpoint: _python_paths(COMPARE_FILE_LIST_LIMIT)}, all_endpoints),
    )
    assert COMPARE_FILE_LIST_LIMIT == 300
    payload = _shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature")
    assert gate.remote_visible_changed_files("o/r", "main", "feature") is None
    assert gate.missing_look_reason(payload) == UNREADABLE_CHANGES_REASON
    assert all_endpoints == [compare_endpoint, compare_endpoint]


def test_should_allow_a_short_compare_page_that_lists_only_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    monkeypatch.setattr(
        gate,
        "_gh_api_lines",
        _fake_gh_api({compare_endpoint: _python_paths(COMPARE_FILE_LIST_LIMIT - 1)}, all_endpoints),
    )
    payload = _shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature")
    assert gate.remote_visible_changed_files("o/r", "main", "feature") == []
    assert gate.missing_look_reason(payload) is None


def test_should_deny_a_visible_file_on_a_full_compare_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    all_paths = [*_python_paths(COMPARE_FILE_LIST_LIMIT - 1), "web/page.html"]
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({compare_endpoint: all_paths}, all_endpoints))
    reason = gate.missing_look_reason(_shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature"))
    assert reason is not None
    assert "web/page.html" in reason
    assert "module_0.py" not in reason


def test_should_allow_a_page_the_compare_api_lists_when_the_proof_links_an_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({compare_endpoint: ["page.html"]}, all_endpoints))
    body_path = tmp_path / "body.md"
    body_path.write_text(PROVEN_BODY + "https://claude.ai/code/artifact/abc-123\n", encoding="utf-8")
    payload = _shell(
        f"gh pr create --title t --body-file {body_path} --repo o/r --base main --head feature",
        tmp_path,
    )
    assert gate.missing_look_reason(payload) is None
    assert all_endpoints == [compare_endpoint]


def test_should_skip_the_compare_api_without_a_named_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({}, all_endpoints))
    payload = _shell_create_elsewhere(tmp_path, "--base main --head feature")
    assert gate.missing_look_reason(payload) == UNREADABLE_CHANGES_REASON
    assert all_endpoints == []


def test_should_read_owner_and_repo_of_an_mcp_create_for_the_compare_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api({compare_endpoint: ["tool.py"]}, all_endpoints))
    payload = _mcp_create_on_branch(PROVEN_BODY, tmp_path)
    payload["tool_input"].update(owner="o", repo="r", base="main")
    assert gate.missing_look_reason(payload) is None
    assert all_endpoints == [compare_endpoint]


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


EVALUATED_BODY = SEARCHED_BODY + "\n## Eval\nTen labeled cases, exact-match grader. Ran `python eval.py`: 10/10.\n"
EVAL_WITHOUT_COMMAND_BODY = SEARCHED_BODY + "\n## Eval\nTen labeled cases, all pass.\n"


def _titled_mcp_create(title: object, body: object) -> dict[str, object]:
    payload = _mcp_create(body)
    payload["tool_input"]["title"] = title
    return payload


def test_feature_mcp_create_without_an_eval_section_should_be_denied() -> None:
    payload = _titled_mcp_create("feat: add a gate", SEARCHED_BODY)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_feature_mcp_create_with_an_eval_section_naming_a_command_should_pass() -> None:
    assert gate.missing_eval_section_reason(_titled_mcp_create("feat: add a gate", EVALUATED_BODY)) is None


def test_feature_mcp_create_with_an_eval_heading_and_no_backtick_should_be_denied() -> None:
    payload = _titled_mcp_create("feat: add a gate", EVAL_WITHOUT_COMMAND_BODY)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_eval_section_should_stop_at_a_heading_of_the_same_level() -> None:
    body = SEARCHED_BODY + "\n## Evals\nCases listed.\n\n## Notes\nRan `python eval.py`.\n"
    payload = _titled_mcp_create("feat: add a gate", body)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_fix_and_docs_titles_without_an_eval_section_should_pass() -> None:
    for each_title in ("fix: repair a gate", "docs: describe a gate"):
        payload = _titled_mcp_create(each_title, SEARCHED_BODY)
        assert gate.missing_eval_section_reason(payload) is None, each_title
        assert not gate.is_feature_pull_request(payload), each_title


def test_feature_titles_should_count_as_features() -> None:
    for each_title in ("feat: x", "feat(hooks)!: x", "FEAT: x", "FEAT(x)!: y", "  feat!: x"):
        assert gate.is_feature_pull_request(_titled_mcp_create(each_title, SEARCHED_BODY)), each_title


def test_non_feature_titles_should_not_count_as_features() -> None:
    for each_title in ("featured: x", "feature: x", "chore: feat: x", None, 7):
        assert not gate.is_feature_pull_request(_titled_mcp_create(each_title, SEARCHED_BODY)), each_title


def test_gh_create_title_flag_should_be_read(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text(SEARCHED_BODY, encoding="utf-8")
    payload = _shell('gh pr create --title "feat: x" --body-file b.md', tmp_path)
    assert gate.is_feature_pull_request(payload)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_gh_create_title_assignment_should_be_read(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text(EVALUATED_BODY, encoding="utf-8")
    payload = _shell("gh pr create --title=feat:x --body-file b.md", tmp_path)
    assert gate.is_feature_pull_request(payload)
    assert gate.missing_eval_section_reason(payload) is None


def test_pull_request_script_create_title_should_be_read(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text(SEARCHED_BODY, encoding="utf-8")
    payload = _shell(
        'python pull_request.py create --title "feat(x): y" --body-file b.md --repo o/r', tmp_path
    )
    assert gate.is_feature_pull_request(payload)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_gh_create_without_a_title_should_not_count_as_a_feature(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text(SEARCHED_BODY, encoding="utf-8")
    payload = _shell("gh pr create --body-file b.md", tmp_path)
    assert not gate.is_feature_pull_request(payload)
    assert gate.missing_eval_section_reason(payload) is None


def test_feature_create_with_an_unreadable_body_should_leave_the_deny_to_the_proof_check() -> None:
    payload = _shell('gh pr create --title "feat: x" --fill')
    assert gate.missing_eval_section_reason(payload) is None
    assert gate.missing_proof_reason(payload) == MISSING_BODY_REASON


def _dispatch(all_inputs: dict[str, object], method: str = "run_workflow") -> dict[str, object]:
    return {
        "tool_name": "mcp__github__actions_run_trigger",
        "tool_input": {
            "method": method,
            "owner": "o",
            "repo": "r",
            "workflow_id": "open.yml",
            "ref": "main",
            "inputs": all_inputs,
        },
    }


def test_pull_request_dispatch_without_proof_should_be_denied() -> None:
    payload = _dispatch({"head": "feature", "title": "fix: y", "body": UNPROVEN_BODY})
    assert gate.missing_proof_reason(payload) == MISSING_PROOF_REASON


def test_pull_request_dispatch_with_no_body_input_should_be_denied() -> None:
    assert gate.missing_proof_reason(_dispatch({"head": "feature", "title": "fix: y"})) == MISSING_PROOF_REASON


def test_feature_dispatch_without_an_eval_section_should_be_denied() -> None:
    payload = _dispatch({"head": "feature", "title": "feat: x", "body": SEARCHED_BODY})
    assert gate.is_feature_pull_request(payload)
    assert gate.missing_eval_section_reason(payload) == MISSING_EVAL_SECTION_REASON


def test_dispatch_that_names_no_head_or_runs_no_workflow_should_not_count_as_a_create() -> None:
    all_payloads = [
        _dispatch({"title": "feat: x", "body": UNPROVEN_BODY}),
        _dispatch({"head": "feature", "title": "feat: x", "body": UNPROVEN_BODY}, "rerun_workflow_run"),
    ]
    for each_payload in all_payloads:
        assert gate.missing_proof_reason(each_payload) is None
        assert not gate.is_feature_pull_request(each_payload)


def test_is_create_call_should_name_shell_and_mcp_creates() -> None:
    assert gate.is_create_call(_shell("gh pr create --title t --body b"))
    assert gate.is_create_call(_mcp_create("b"))
    assert not gate.is_create_call(_shell("gh pr edit 7 --body b"))
    assert not gate.is_create_call({"tool_name": "Read", "tool_input": {"file_path": "a.py"}})
WORKFLOW_DIRECTORY = ".github/workflows"
NEW_WORKFLOW_NAME = "release-hold.yml"
UNPROVEN_RUN_LINE = "Not proven here: the live GitHub Actions run."
AFTER_MERGE_SECTION = (
    "\n## After merge\n\n- The first owner approval runs `release-hold.yml`."
    " The agent driving this change records that run link on this pull request.\n"
)


def _workflow_body(after_merge_section: str) -> str:
    return (
        "## Proof in practice\nRan `python run.py`.\n"
        + UNPROVEN_RUN_LINE
        + "\n"
        + after_merge_section
    )


def _repository_with_workflow_change(
    tmp_path: Path, changed_workflow_name: str
) -> Path:
    origin_path = tmp_path / "origin"
    clone_path = tmp_path / "clone"
    git_identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin_path)], check=True)
    (origin_path / WORKFLOW_DIRECTORY).mkdir(parents=True)
    (origin_path / WORKFLOW_DIRECTORY / "ci.yml").write_text(
        "name: ci\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(origin_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(origin_path), *git_identity, "commit", "-q", "-m", "base"],
        check=True,
    )
    subprocess.run(
        ["git", "clone", "-q", str(origin_path), str(clone_path)], check=True
    )
    subprocess.run(
        ["git", "-C", str(clone_path), "checkout", "-q", "-b", "feature"], check=True
    )
    (clone_path / WORKFLOW_DIRECTORY / changed_workflow_name).write_text(
        "name: changed\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(clone_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(clone_path), *git_identity, "commit", "-q", "-m", "change"],
        check=True,
    )
    return clone_path


def test_unproven_line_should_pass_when_a_new_workflow_names_its_after_merge_run(
    tmp_path: Path,
) -> None:
    clone_path = _repository_with_workflow_change(tmp_path, NEW_WORKFLOW_NAME)
    payload = _mcp_create_on_branch(_workflow_body(AFTER_MERGE_SECTION), clone_path)
    assert gate.missing_proof_reason(payload) is None


def test_unproven_line_should_stay_denied_when_the_branch_only_edits_an_existing_workflow(
    tmp_path: Path,
) -> None:
    clone_path = _repository_with_workflow_change(tmp_path, "ci.yml")
    after_merge_section = AFTER_MERGE_SECTION.replace(NEW_WORKFLOW_NAME, "ci.yml")
    payload = _mcp_create_on_branch(_workflow_body(after_merge_section), clone_path)
    assert gate.missing_proof_reason(payload) == UNPROVEN_PROOF_REASON.format(
        admission=UNPROVEN_RUN_LINE
    )


@pytest.mark.parametrize(
    "after_merge_section",
    [
        "",
        "\n## After merge\n\n- The first owner approval runs `other.yml`. The agent records the link.\n",
        "\n## After merge\n\n- The first owner approval runs `release-hold.yml`.\n",
        "\n## After merge\n\n- The first owner approval runs release-hold.yml. The agent records the link.\n",
    ],
    ids=[
        "no-section",
        "other-workflow-named",
        "no-recorder",
        "workflow-not-in-backticks",
    ],
)
def test_unproven_line_should_stay_denied_when_the_after_merge_section_falls_short(
    tmp_path: Path, after_merge_section: str
) -> None:
    clone_path = _repository_with_workflow_change(tmp_path, NEW_WORKFLOW_NAME)
    payload = _mcp_create_on_branch(_workflow_body(after_merge_section), clone_path)
    assert gate.missing_proof_reason(payload) == UNPROVEN_PROOF_REASON.format(
        admission=UNPROVEN_RUN_LINE
    )


def test_unproven_line_should_stay_denied_when_git_cannot_read_the_branch(
    tmp_path: Path,
) -> None:
    payload = _mcp_create_on_branch(_workflow_body(AFTER_MERGE_SECTION), tmp_path)
    assert gate.missing_proof_reason(payload) == UNPROVEN_PROOF_REASON.format(
        admission=UNPROVEN_RUN_LINE
    )


def test_added_workflow_files_should_list_only_files_the_branch_adds(
    tmp_path: Path,
) -> None:
    added_clone = _repository_with_workflow_change(
        tmp_path / "added", NEW_WORKFLOW_NAME
    )
    edited_clone = _repository_with_workflow_change(tmp_path / "edited", "ci.yml")
    assert gate.added_workflow_files(str(added_clone), "feature") == [
        f"{WORKFLOW_DIRECTORY}/{NEW_WORKFLOW_NAME}"
    ]
    assert gate.added_workflow_files(str(edited_clone), "feature") == []
    assert gate.added_workflow_files(str(added_clone), "other-branch") is None


def _workflow_compare_lines(count: int, all_added_paths: list[str]) -> list[str]:
    return [str(count), *all_added_paths]


def test_unproven_line_should_pass_on_the_compare_api_when_a_new_workflow_is_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    compare_endpoint = "repos/o/r/compare/main...feature"
    added_path = f"{WORKFLOW_DIRECTORY}/{NEW_WORKFLOW_NAME}"
    all_responses = {compare_endpoint: _workflow_compare_lines(2, [added_path])}
    monkeypatch.setattr(
        gate, "_gh_api_lines", _fake_gh_api(all_responses, all_endpoints)
    )
    payload = _shell_create_elsewhere(tmp_path, "--repo o/r --base main --head feature")
    body_path = tmp_path / "body.md"
    body_path.write_text(_workflow_body(AFTER_MERGE_SECTION), encoding="utf-8")
    assert gate.remote_added_workflow_files("o/r", "main", "feature") == [added_path]
    assert gate.missing_proof_reason(payload) is None


def test_remote_added_workflow_files_should_report_none_when_a_full_page_lists_no_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compare_endpoint = "repos/o/r/compare/main...feature"
    all_responses = {
        compare_endpoint: _workflow_compare_lines(
            COMPARE_FILE_LIST_LIMIT, ["pkg/module_0.py"]
        ),
    }
    monkeypatch.setattr(gate, "_gh_api_lines", _fake_gh_api(all_responses, []))
    assert gate.remote_added_workflow_files("o/r", "main", "feature") is None
    all_responses[compare_endpoint] = _workflow_compare_lines(
        COMPARE_FILE_LIST_LIMIT - 1, ["pkg/module_0.py"]
    )
    assert gate.remote_added_workflow_files("o/r", "main", "feature") == []
    assert gate.remote_added_workflow_files(None, "main", "feature") is None
