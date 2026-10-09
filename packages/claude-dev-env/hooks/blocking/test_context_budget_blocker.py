"""The context budget write hook denies only what an edit adds to agent context."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking.context_budget_blocker import evaluate

FIXTURE_DIRECTORY = HOOKS_DIRECTORY / "test_files" / "context_budget"
DISPATCHER_PATH = HOOKS_DIRECTORY / "blocking" / "pre_tool_use_dispatcher.py"
ORCHESTRATOR_RELATIVE_PATH = "packages/claude-dev-env/.agents/skills/orchestrator/SKILL.md"
OVER_LIMIT_DETAIL = "".join(f"Detail line {each}.\n" for each in range(9))


def _fixture_text(file_name: str) -> str:
    return (FIXTURE_DIRECTORY / file_name).read_text(encoding="utf-8")


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "other-repository"
    (root / ".git").mkdir(parents=True)
    return root


def _write_payload(file_path: Path, content: str) -> dict[str, object]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path), "content": content},
    }


def _edit_payload(file_path: Path, old_string: str, new_string: str) -> dict[str, object]:
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(file_path),
            "old_string": old_string,
            "new_string": new_string,
        },
    }


def _over_budget_skill() -> str:
    return "# Skill\n## Plan\n" + OVER_LIMIT_DETAIL + "filler\n" * 200


def test_calibration_old_revision_is_denied_and_new_revision_allowed(repository_root: Path) -> None:
    target_path = repository_root / ORCHESTRATOR_RELATIVE_PATH

    old_reason = evaluate(
        _write_payload(target_path, _fixture_text("orchestrator_skill_3f2c3ef.txt"))
    )
    new_reason = evaluate(
        _write_payload(target_path, _fixture_text("orchestrator_skill_98f45b1.txt"))
    )

    assert old_reason is not None
    assert (
        'section "Oversee delegated work" has 9 detail lines and no pointer (limit 6)' in old_reason
    )
    assert new_reason is None


def test_edit_that_only_shrinks_an_over_budget_file_is_allowed(repository_root: Path) -> None:
    target_path = repository_root / "skills" / "big" / "SKILL.md"
    target_path.parent.mkdir(parents=True)
    target_path.write_text(_over_budget_skill(), encoding="utf-8")

    assert evaluate(_edit_payload(target_path, "filler\nfiller\n", "")) is None


def test_edit_that_grows_an_over_budget_file_is_denied(repository_root: Path) -> None:
    target_path = repository_root / "skills" / "big" / "SKILL.md"
    target_path.parent.mkdir(parents=True)
    target_path.write_text(_over_budget_skill(), encoding="utf-8")

    reason = evaluate(_edit_payload(target_path, "# Skill\n", "# Skill\nOne more line.\n"))

    assert reason is not None
    assert "was already over its limit at 211 lines and may only shrink" in reason
    assert "list" not in reason


def test_edit_that_adds_a_line_to_a_short_skill_with_one_long_section_is_allowed(
    repository_root: Path,
) -> None:
    target_path = repository_root / "skills" / "short" / "SKILL.md"
    target_path.parent.mkdir(parents=True)
    plan_body = "".join(f"Detail line {each}.\n" for each in range(8))
    target_path.write_text("# Skill\nIntro.\n## Plan\n" + plan_body, encoding="utf-8")

    assert len(target_path.read_text(encoding="utf-8").splitlines()) == 11
    assert evaluate(_edit_payload(target_path, "Intro.\n", "Intro.\nOne more line.\n")) is None


def test_multi_edit_adding_an_unpointed_section_is_denied(repository_root: Path) -> None:
    target_path = repository_root / "AGENTS.md"
    target_path.write_text("# Agents\nShort.\n", encoding="utf-8")
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(target_path),
            "edits": [
                {"old_string": "Short.\n", "new_string": "Short.\n## Steps\n" + OVER_LIMIT_DETAIL}
            ],
        },
    }

    reason = evaluate(payload)

    assert reason is not None and 'section "Steps"' in reason


def test_apply_patch_adding_an_over_budget_rule_is_denied(repository_root: Path) -> None:
    patch_lines = ["*** Begin Patch", "*** Add File: rules/long.md"]
    patch_lines.extend(f"+Rule line {each}." for each in range(31))
    patch_lines.append("*** End Patch")
    payload = {
        "tool_name": "apply_patch",
        "cwd": str(repository_root),
        "tool_input": {"command": "\n".join(patch_lines) + "\n"},
    }

    reason = evaluate(payload)

    assert reason is not None and "file has 31 lines (rule limit 30)" in reason


def test_policy_file_of_the_edited_repository_supplies_kinds_and_baseline(
    repository_root: Path,
) -> None:
    (repository_root / ".claude").mkdir()
    policy = {
        "kinds": [
            {"name": "guide", "patterns": ["docs/*.md"], "line_limit": 3, "section_rule": False}
        ],
        "baseline": {"files": {"docs/a.md": {"lines": 5, "sections": []}}},
    }
    (repository_root / ".claude" / "context-budget.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    target_path = repository_root / "docs" / "a.md"

    assert evaluate(_write_payload(target_path, "1\n2\n3\n4\n5\n")) is None
    reason = evaluate(_write_payload(target_path, "1\n2\n3\n4\n5\n6\n"))
    assert reason is not None and "grew from 5 to 6 lines" in reason
    assert evaluate(_write_payload(repository_root / "SKILL.md", OVER_LIMIT_DETAIL * 30)) is None


def test_malformed_policy_file_falls_back_to_the_built_in_kinds(repository_root: Path) -> None:
    (repository_root / ".claude").mkdir()
    (repository_root / ".claude" / "context-budget.json").write_text("{broken", encoding="utf-8")

    reason = evaluate(_write_payload(repository_root / "rules" / "r.md", "x\n" * 31))

    assert reason is not None and "rule limit 30" in reason


def test_files_outside_context_or_any_repository_are_allowed(
    repository_root: Path, tmp_path: Path
) -> None:
    assert evaluate(_write_payload(repository_root / "notes.txt", "x\n" * 999)) is None
    assert evaluate(_write_payload(tmp_path / "loose" / "SKILL.md", OVER_LIMIT_DETAIL * 99)) is None


def test_dispatcher_carries_the_denial(repository_root: Path) -> None:
    payload = _write_payload(repository_root / "rules" / "r.md", "x\n" * 31)

    completed_process = subprocess.run(
        [sys.executable, str(DISPATCHER_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )

    decision = json.loads(completed_process.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "[CONTEXT_BUDGET]" in decision["permissionDecisionReason"]
