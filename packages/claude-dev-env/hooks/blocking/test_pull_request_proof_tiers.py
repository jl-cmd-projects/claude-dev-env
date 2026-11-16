"""Behavior tests for the evidence tiers the pull request proof and Eval checks apply."""

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pr_lifecycle_skill_gate as lifecycle_gate
from blocking import pull_request_proof as gate
from blocking.evidence_tier import TierCause, TierChoice
from blocking.gate_run_reads import gate_run
from hooks_constants.pull_request_proof_constants import (
    COMPARE_FILE_LIST_LIMIT,
    MISSING_BUILD_EVAL_REASON,
    MISSING_CHECKED_PROOF_REASON,
    MISSING_EVAL_SECTION_REASON,
    MISSING_PROOF_REASON,
    TEST_ONLY_PROOF_REASON,
)
from hooks_constants import pull_request_proof_constants as proof_constants

GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
TEST_RUN_PROOF_BODY = "## Proof in practice\nRan `python -m pytest tests -q`.\n> 3 passed\n"
LIVE_PROOF_BODY = "## Proof in practice\nRan `python run.py --input a.txt`.\n> denied\n"
NO_PROOF_BODY = "## Summary\nRewords the guide.\n"
EMPTY_PROOF_BODY = "## Summary\nRewords the guide.\n\n## Proof in practice\n\n## Risk\nNone.\n"
NO_COMMAND_PROOF_BODY = "## Proof in practice\nRead the page again.\n"
EVAL_LESS_BODY = TEST_RUN_PROOF_BODY + "\n## Existing work\nNothing found.\n"
DECLARED_SURFACES = "# code that reaches the seller portal\nportal/\n"


def _git(repository_path: Path, *all_arguments: str) -> None:
    subprocess.run(["git", "-C", str(repository_path), *GIT_IDENTITY, *all_arguments], check=True)


def _write_files(repository_path: Path, all_texts_by_path: dict[str, str]) -> None:
    for each_path, each_text in all_texts_by_path.items():
        file_path = repository_path / each_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(each_text, encoding="utf-8")


def _clone_with_branch(
    tmp_path: Path,
    all_branch_texts_by_path: dict[str, str],
    all_base_texts_by_path: dict[str, str] | None = None,
    all_moves: tuple[tuple[str, str], ...] = (),
) -> Path:
    origin_path = tmp_path / "origin"
    clone_path = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin_path)], check=True)
    _write_files(origin_path, {"readme.md": "base\n", **(all_base_texts_by_path or {})})
    _git(origin_path, "add", ".")
    _git(origin_path, "commit", "-q", "-m", "base")
    subprocess.run(["git", "clone", "-q", str(origin_path), str(clone_path)], check=True)
    _git(clone_path, "checkout", "-q", "-b", "feature")
    for each_old_path, each_new_path in all_moves:
        (clone_path / each_new_path).parent.mkdir(parents=True, exist_ok=True)
        _git(clone_path, "mv", each_old_path, each_new_path)
    _write_files(clone_path, all_branch_texts_by_path)
    _git(clone_path, "add", ".")
    _git(clone_path, "commit", "-q", "-m", "change")
    return clone_path


def _create_from(
    clone_path: Path, body: str, title: str = "fix: tighten a check"
) -> dict[str, object]:
    body_path = clone_path.parent / "body.md"
    body_path.write_text(body, encoding="utf-8")
    return {
        "tool_name": "Bash",
        "tool_input": {"command": f'gh pr create --title "{title}" --body-file "{body_path}"'},
        "cwd": str(clone_path),
    }


def _edit_from(clone_path: Path, body: str, selector: str = "") -> dict[str, object]:
    body_path = clone_path.parent / "edit-body.md"
    body_path.write_text(body, encoding="utf-8")
    return {
        "tool_name": "Bash",
        "tool_input": {"command": f'gh pr edit {selector} --body-file "{body_path}"'},
        "cwd": str(clone_path),
    }


def test_should_pass_a_docs_only_create_with_no_proof_section(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"docs/guide.md": "new words\n", "tests/test_a.py": "x = 1\n"}
    )
    assert gate.missing_proof_reason(_create_from(clone_path, NO_PROOF_BODY)) is None


def test_should_check_a_proof_section_a_docs_only_create_keeps(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    reason = gate.missing_proof_reason(_create_from(clone_path, EMPTY_PROOF_BODY))
    assert reason == MISSING_CHECKED_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.ONLY_DOCS_AND_TESTS, None)
    )


def test_should_pass_a_code_create_whose_proof_is_a_test_run_when_no_declared_surface_matches(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    assert gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY)) is None


def test_should_deny_a_code_create_with_no_proof_section_naming_the_checked_tier(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    reason = gate.missing_proof_reason(_create_from(clone_path, NO_COMMAND_PROOF_BODY))
    assert reason == MISSING_CHECKED_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.CODE_WITHOUT_LIVE_SURFACE, "src/gate.py")
    )
    assert "checked" in reason
    assert "src/gate.py" in reason


def test_should_deny_a_test_run_proof_for_code_when_the_base_declares_no_surfaces(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(tmp_path, {"src/gate.py": "x = 2\n"})
    reason = gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.NO_DECLARED_SURFACES, "src/gate.py")
    )


def test_should_deny_a_test_run_proof_for_a_skill_change_naming_the_skill_path(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(
        tmp_path,
        {"src/gate.py": "x = 2\n", "skills/ship/SKILL.md": "# Ship\n"},
        {".claude/live-surfaces.txt": DECLARED_SURFACES},
    )
    reason = gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.LIVE_SURFACE, "skills/ship/SKILL.md")
    )
    assert "skills/ship/SKILL.md" in reason


def test_should_deny_a_test_run_proof_for_a_path_the_base_declares(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"portal/client.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    reason = gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY))
    assert reason is not None and reason.startswith(TEST_ONLY_PROOF_REASON)
    assert "portal/client.py" in reason


def test_should_read_the_declared_surfaces_from_the_base_and_not_the_working_tree(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"portal/client.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    (clone_path / ".claude" / "live-surfaces.txt").write_text(
        "# nothing is live\n", encoding="utf-8"
    )
    reason = gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY))
    assert reason is not None and reason.startswith(TEST_ONLY_PROOF_REASON)


def test_should_keep_the_live_tier_when_a_skill_moves_out_of_its_folder(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path,
        {},
        {"skills/ship/notes.md": "steps\n", ".claude/live-surfaces.txt": DECLARED_SURFACES},
        (("skills/ship/notes.md", "archive/notes.md"),),
    )
    reason = gate.missing_proof_reason(_create_from(clone_path, NO_PROOF_BODY))
    assert reason == MISSING_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.LIVE_SURFACE, "skills/ship/notes.md")
    )


def test_should_deny_a_test_run_proof_when_the_file_list_cannot_be_read(tmp_path: Path) -> None:
    reason = gate.missing_proof_reason(
        _create_from(tmp_path / "not-a-repository", TEST_RUN_PROOF_BODY)
    )
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.UNREAD_FILE_LIST, None)
    )


def test_should_not_trust_a_checkout_of_another_repository_for_the_tier(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    payload = _create_from(clone_path, NO_PROOF_BODY)
    payload["tool_input"]["command"] += " --repo other/repository"
    reason = gate.missing_proof_reason(payload)
    assert reason == MISSING_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.UNREAD_FILE_LIST, None)
    )


def test_should_not_read_git_when_a_live_proof_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone_path = _clone_with_branch(tmp_path, {"src/gate.py": "x = 2\n"})
    all_git_reads: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        gate, "_git_output", lambda *all_arguments: all_git_reads.append(all_arguments)
    )
    assert gate.missing_proof_reason(_create_from(clone_path, LIVE_PROOF_BODY)) is None
    assert all_git_reads == []


def _compare_line(path: str) -> str:
    return json.dumps(["modified", "", path], separators=(",", ":"))


def _stub_remote(
    monkeypatch: pytest.MonkeyPatch, all_compare_lines: list[str], declared_text: str | None
) -> None:
    contents_lines = (
        None if declared_text is None else [base64.b64encode(declared_text.encode()).decode()]
    )
    all_responses = {
        "repos/o/r/compare/main...feature": all_compare_lines,
        "repos/o/r/contents/.claude/live-surfaces.txt?ref=main": contents_lines,
    }
    monkeypatch.setattr(gate, "_gh_api_lines", lambda endpoint, query: all_responses.get(endpoint))


def _remote_create(
    tmp_path: Path, body: str, title: str = "fix: tighten a check"
) -> dict[str, object]:
    body_path = tmp_path / "body.md"
    body_path.write_text(body, encoding="utf-8")
    return {
        "tool_name": "Bash",
        "tool_input": {
            "command": f'gh pr create --repo o/r --base main --head feature --title "{title}" --body-file "{body_path}"'
        },
        "cwd": str(tmp_path),
    }


def test_should_take_the_tier_from_the_compare_api_and_the_base_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_remote(monkeypatch, [_compare_line("src/gate.py")], DECLARED_SURFACES)
    assert gate.missing_proof_reason(_remote_create(tmp_path, TEST_RUN_PROOF_BODY)) is None


def test_should_give_live_at_the_compare_file_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_lines = [
        _compare_line(f"src/m{each_index}.py") for each_index in range(COMPARE_FILE_LIST_LIMIT)
    ]
    _stub_remote(monkeypatch, all_lines, DECLARED_SURFACES)
    reason = gate.missing_proof_reason(_remote_create(tmp_path, TEST_RUN_PROOF_BODY))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.UNREAD_FILE_LIST, None)
    )


def test_should_give_live_for_remote_code_when_the_base_contents_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_remote(monkeypatch, [_compare_line("src/gate.py")], None)
    reason = gate.missing_proof_reason(_remote_create(tmp_path, TEST_RUN_PROOF_BODY))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.NO_DECLARED_SURFACES, "src/gate.py")
    )


def test_should_read_the_changed_files_once_for_the_tier_and_the_picture_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_endpoints: list[str] = []
    all_responses = {"repos/o/r/compare/main...feature": [_compare_line("src/gate.py")]}

    def counting_gh_api_lines(endpoint: str, query: str) -> list[str] | None:
        all_endpoints.append(endpoint)
        return all_responses.get(endpoint)

    monkeypatch.setattr(gate, "_gh_api_lines", counting_gh_api_lines)
    payload = _remote_create(tmp_path, TEST_RUN_PROOF_BODY)
    with gate_run():
        gate.missing_proof_reason(payload)
        gate.missing_look_reason(payload)
    assert all_endpoints.count("repos/o/r/compare/main...feature") == 1


def test_should_skip_the_eval_section_for_a_feature_that_changes_only_plain_code(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(tmp_path, {"src/gate.py": "x = 2\n"})
    payload = _create_from(clone_path, EVAL_LESS_BODY, "feat: add a check")
    assert gate.missing_eval_section_reason(payload) is None


def test_should_deny_a_feature_that_changes_a_skill_without_an_eval_section(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n", "skills/ship/SKILL.md": "# Ship\n"}
    )
    reason = gate.missing_eval_section_reason(
        _create_from(clone_path, EVAL_LESS_BODY, "feat: add a check")
    )
    assert reason == MISSING_EVAL_SECTION_REASON + gate.eval_owed_sentence(
        "skills/ship/SKILL.md"
    )


def test_should_keep_the_eval_section_for_a_feature_whose_file_list_cannot_be_read(
    tmp_path: Path,
) -> None:
    payload = _create_from(tmp_path / "not-a-repository", EVAL_LESS_BODY, "feat: add a check")
    reason = gate.missing_eval_section_reason(payload)
    assert reason == MISSING_EVAL_SECTION_REASON + gate.eval_owed_sentence(None)


SKILL_LOAD_LINE = json.dumps(
    {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "pr-lifecycle"}}]
        },
    }
)
FULL_BODY_TAIL = "\n## What this does\n```mermaid\nflowchart LR\n  a --> b\n```\n\n## Existing work\nNothing found.\n"


def _gate_payload(clone_path: Path, title: str) -> dict[str, object]:
    transcript_path = clone_path.parent / "session.jsonl"
    transcript_path.write_text(SKILL_LOAD_LINE + "\n", encoding="utf-8")
    payload = _create_from(clone_path, TEST_RUN_PROOF_BODY + FULL_BODY_TAIL, title)
    payload["transcript_path"] = str(transcript_path)
    return payload


def test_should_not_ask_for_build_eval_on_a_feature_that_changes_only_plain_code(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    assert lifecycle_gate.decision_for(_gate_payload(clone_path, "feat: add a check")) is None


def test_should_ask_for_build_eval_on_a_feature_that_changes_a_rule(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"rules/ship.md": "Ship it.\n"})
    payload = _gate_payload(clone_path, "feat: add a rule")
    (clone_path.parent / "body.md").write_text(
        LIVE_PROOF_BODY + FULL_BODY_TAIL + "\n## Eval\nTen cases. Ran `python grade.py`: 10/10.\n",
        encoding="utf-8",
    )
    decision = lifecycle_gate.decision_for(payload)
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == (
        MISSING_BUILD_EVAL_REASON + gate.eval_owed_sentence("rules/ship.md")
    )


def test_should_take_an_edit_tier_from_the_checkout_of_the_pull_request(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    assert gate.edit_proof_reason(_edit_from(clone_path, TEST_RUN_PROOF_BODY)) is None


def test_should_deny_an_edit_that_swaps_in_a_proof_its_tier_would_deny(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    reason = gate.edit_proof_reason(_edit_from(clone_path, NO_COMMAND_PROOF_BODY))
    assert reason == MISSING_CHECKED_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.ONLY_DOCS_AND_TESTS, None)
    )


def test_should_apply_the_live_rule_to_an_edit_that_names_another_pull_request(
    tmp_path: Path,
) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    reason = gate.edit_proof_reason(_edit_from(clone_path, TEST_RUN_PROOF_BODY, "7"))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.NAMED_PULL_REQUEST_EDIT, None)
    )
    assert "gh pr edit" in reason


def test_should_apply_the_live_rule_to_a_script_edit_of_a_checked_tier_pull_request(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    body_path = clone_path.parent / "edit-body.md"
    body_path.write_text(TEST_RUN_PROOF_BODY, encoding="utf-8")
    payload = {
        "tool_name": "Bash",
        "tool_input": {
            "command": f'python pull_request.py edit --repo o/r --number 7 --body-file "{body_path}"'
        },
        "cwd": str(clone_path),
    }
    assert gate.missing_proof_reason(_create_from(clone_path, TEST_RUN_PROOF_BODY)) is None
    assert gate.edit_proof_reason(payload) == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.NAMED_PULL_REQUEST_EDIT, None)
    )


def test_should_apply_the_live_rule_to_an_update_tool_edit() -> None:
    payload = {
        "tool_name": "mcp__github__update_pull_request",
        "tool_input": {"owner": "o", "repo": "r", "pullNumber": 7, "body": TEST_RUN_PROOF_BODY},
    }
    reason = gate.edit_proof_reason(payload)
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.NAMED_PULL_REQUEST_EDIT, None)
    )


def test_checkout_sections_should_print_what_the_checkout_owes(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    printed = subprocess.run(
        [sys.executable, str(Path(gate.__file__)), str(clone_path)],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert json.loads(printed) == {
        "needs_proof_section": False,
        "needs_eval_section_for_a_feature": False,
    }


def test_checkout_sections_should_ask_for_both_sections_when_the_list_cannot_be_read(
    tmp_path: Path,
) -> None:
    printed = subprocess.run(
        [sys.executable, str(Path(gate.__file__)), str(tmp_path)],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert json.loads(printed) == {
        "needs_proof_section": True,
        "needs_eval_section_for_a_feature": True,
    }


def _payload_with_command(clone_path: Path, command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(clone_path)}


def _create_command(clone_path: Path, body: str, title: str = "fix: tighten a check") -> str:
    body_path = clone_path.parent / "body.md"
    body_path.write_text(body, encoding="utf-8")
    return f'gh pr create --title "{title}" --body-file "{body_path}"'


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ('git commit -q -m "skill" && ', ""),
        ("git checkout -q main && ", ""),
        ('cd "{clone}" && ', ""),
        ("git add -A; ", ""),
        ("git add -A\n", ""),
        ("", " || true"),
        ("", " | tee out.txt"),
        ("(", ")"),
        ('bash -c "', '"'),
    ],
)
def test_should_give_the_live_tier_to_a_create_that_shares_its_command(
    tmp_path: Path, prefix: str, suffix: str
) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    create_command = _create_command(clone_path, NO_PROOF_BODY).replace('"', "'")
    command = prefix.format(clone=clone_path) + create_command + suffix
    reason = gate.missing_proof_reason(_payload_with_command(clone_path, command))
    assert reason == MISSING_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.SHARED_COMMAND, None)
    )
    assert "alone" in reason


@pytest.mark.parametrize(
    "title",
    ["docs: a && b; c | d", "docs: reword the guide"],
)
def test_should_read_the_tier_for_a_create_that_runs_alone(tmp_path: Path, title: str) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    command = _create_command(clone_path, NO_PROOF_BODY, title) + "\n"
    assert gate.missing_proof_reason(_payload_with_command(clone_path, command)) is None


def test_should_owe_an_eval_for_a_feature_create_that_shares_its_command(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    command = "git add -A && " + _create_command(clone_path, EVAL_LESS_BODY, "feat: add a check")
    reason = gate.missing_eval_section_reason(_payload_with_command(clone_path, command))
    assert reason == MISSING_EVAL_SECTION_REASON + proof_constants.SHARED_COMMAND_EVAL_SENTENCE


def test_should_give_the_live_tier_to_an_edit_that_shares_its_command(tmp_path: Path) -> None:
    clone_path = _clone_with_branch(tmp_path, {"docs/guide.md": "new words\n"})
    body_path = clone_path.parent / "edit-body.md"
    body_path.write_text(TEST_RUN_PROOF_BODY, encoding="utf-8")
    command = f'cd "{clone_path}" && gh pr edit --body-file "{body_path}"'
    reason = gate.edit_proof_reason(_payload_with_command(clone_path, command))
    assert reason == TEST_ONLY_PROOF_REASON + gate.tier_sentence(
        TierChoice(TierCause.SHARED_COMMAND, None)
    )


def test_should_skip_the_build_eval_scan_for_a_feature_that_owes_no_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone_path = _clone_with_branch(
        tmp_path, {"src/gate.py": "x = 2\n"}, {".claude/live-surfaces.txt": DECLARED_SURFACES}
    )
    all_scanned_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(lifecycle_gate, "is_build_eval_missing", all_scanned_payloads.append)
    assert lifecycle_gate.decision_for(_gate_payload(clone_path, "feat: add a check")) is None
    assert all_scanned_payloads == []
