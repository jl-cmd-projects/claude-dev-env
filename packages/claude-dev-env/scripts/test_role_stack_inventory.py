"""The inventory rejects an eval retirement that drops the reproducible check."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from dev_env_scripts_constants.role_stack_inventory_constants import (
    FINDING_BEHAVIOR_STILL_ACTIVE,
    FINDING_DROPS_REPRODUCIBLE_CHECK,
    FINDING_MARKS_EVALS_OPTIONAL,
    REPRODUCIBLE_CHECK_SENTENCE,
)
from role_stack_inventory import (
    findings_for_rows,
    inventory_findings,
    replacement_rows,
    reproducible_check_findings,
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_KEPT_REQUIREMENT = (
    f"{REPRODUCIBLE_CHECK_SENTENCE} "
    "Red before the fix, the wrong twin fails, and undo fails again. "
    "Only the forced position as the very first action is retired."
)
_KEPT_INSTRUCTION = (
    "The role-stack eval leaf calls this guide after intake. "
    f"{_KEPT_REQUIREMENT}"
)
_FIRST_ACTION = (
    "Your first action is the Skill tool with skill `claude-api` and args `build-eval`"
)


def _row_block(requirement: str, instruction_phrase: str) -> str:
    return textwrap.dedent(
        f"""\
        ## Role stack replacements

        | Retired path | Behavior it required | Trigger that replaces it | Requirement that stays |
        |---|---|---|---|
        | docs/rule-guides/features-start-with-an-eval.md | {instruction_phrase} | role-stack eval leaf | {requirement} |
        """
    )


def test_should_reject_an_instruction_that_marks_evals_optional() -> None:
    findings = reproducible_check_findings(
        "Evals are optional before a done claim.",
        "Evals are optional. The reproducible check is removed.",
        "docs/rule-guides/features-start-with-an-eval.md",
    )
    assert any(each.code == FINDING_MARKS_EVALS_OPTIONAL for each in findings)
    assert any(each.code == FINDING_DROPS_REPRODUCIBLE_CHECK for each in findings)


def test_should_reject_a_manifest_that_removes_the_reproducible_check() -> None:
    findings = reproducible_check_findings(
        _KEPT_INSTRUCTION,
        "Only the forced position as the very first action is retired.",
        "docs/rule-guides/features-start-with-an-eval.md",
    )
    manifest_drops = [
        each
        for each in findings
        if each.code == FINDING_DROPS_REPRODUCIBLE_CHECK and each.detail == "manifest"
    ]
    assert manifest_drops


def test_should_accept_a_retirement_that_keeps_the_reproducible_check() -> None:
    assert reproducible_check_findings(
        _KEPT_INSTRUCTION,
        _KEPT_REQUIREMENT,
        "docs/rule-guides/features-start-with-an-eval.md",
    ) == ()


def test_should_reject_a_tree_whose_guide_still_orders_the_first_action(tmp_path: Path) -> None:
    package_root = tmp_path
    guide = package_root / "docs" / "rule-guides" / "features-start-with-an-eval.md"
    guide.parent.mkdir(parents=True)
    guide.write_text(f"{_FIRST_ACTION}. Build the feature.\n", encoding="utf-8")
    skill = package_root / ".agents" / "skills" / "role-stack" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("role-stack eval leaf\n", encoding="utf-8")
    manifest = package_root / "rules-archived" / "ARCHIVE-MANIFEST.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(_row_block(_KEPT_REQUIREMENT, _FIRST_ACTION), encoding="utf-8")
    all_rows = replacement_rows(manifest.read_text(encoding="utf-8"))
    findings = findings_for_rows(package_root, all_rows, skill.read_text(encoding="utf-8"))
    assert any(each.code == FINDING_BEHAVIOR_STILL_ACTIVE for each in findings)
    assert any(each.code == FINDING_DROPS_REPRODUCIBLE_CHECK for each in findings)


def test_should_accept_a_tree_that_retires_only_the_first_action(tmp_path: Path) -> None:
    package_root = tmp_path
    guide = package_root / "docs" / "rule-guides" / "features-start-with-an-eval.md"
    guide.parent.mkdir(parents=True)
    guide.write_text(_KEPT_INSTRUCTION + "\n", encoding="utf-8")
    skill = package_root / ".agents" / "skills" / "role-stack" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("role-stack eval leaf\n", encoding="utf-8")
    manifest = package_root / "rules-archived" / "ARCHIVE-MANIFEST.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(_row_block(_KEPT_REQUIREMENT, _FIRST_ACTION), encoding="utf-8")
    (package_root / ".agents" / "skills" / "kept").mkdir(parents=True)
    (package_root / ".agents" / "skills" / "kept" / "SKILL.md").write_text(
        "---\nname: kept\n---\n", encoding="utf-8"
    )
    (package_root / "bin").mkdir()
    (package_root / "bin" / "ever-shipped-skills.mjs").write_text("'kept'\n", encoding="utf-8")
    assert inventory_findings(package_root) == ()


def test_live_package_has_no_role_stack_rows_yet() -> None:
    manifest_text = (_PACKAGE_ROOT / "rules-archived" / "ARCHIVE-MANIFEST.md").read_text(
        encoding="utf-8"
    )
    assert replacement_rows(manifest_text) == ()
    completed = subprocess.run(
        [sys.executable, str(_PACKAGE_ROOT / "scripts" / "role_stack_inventory.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_PACKAGE_ROOT),
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
