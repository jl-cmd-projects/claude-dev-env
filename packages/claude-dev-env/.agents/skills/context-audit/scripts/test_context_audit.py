"""Behavior tests for the context audit, run as a command on a temporary git checkout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent / "context_audit.py"


def write_file(root: Path, relative_path: str, text: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def numbered_lines(count: int) -> str:
    return "".join(f"line {each_index}\n" for each_index in range(count))


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "sample-repo"
    write_file(root, "CLAUDE.md", "@AGENTS.md\n@docs/shared.md\n")
    write_file(root, "AGENTS.md", numbered_lines(30))
    write_file(root, "docs/shared.md", "Shared steps. See [deep](deep.md).\n")
    write_file(root, "docs/deep.md", "Deep notes. See [deeper](deeper.md).\n")
    write_file(root, "docs/deeper.md", "Deeper notes.\n")
    write_file(root, "nested/CLAUDE.md", "")
    write_file(
        root,
        ".claude/rules/api.md",
        "---\npaths:\n  - src/api/**\n---\nUse the client.\n",
    )
    write_file(root, ".claude/rules/general.md", "Keep diffs small.\n")
    write_file(
        root,
        ".claude/skills/demo/SKILL.md",
        "---\nname: demo\ndescription: Run the demo. Use when asked to demo.\n---\n"
        + numbered_lines(250),
    )
    write_file(root, ".claude/skills/demo/references/guide.md", "Guide body.\n")
    write_file(
        root,
        ".claude/skills/quiet/SKILL.md",
        "---\nname: quiet\ndescription: Hidden.\ndisable-model-invocation: true\n---\nBody.\n",
    )
    write_file(
        root, "tests/fixture/.claude/skills/ghost/SKILL.md", "---\nname: ghost\n---\n"
    )
    write_file(root, "tool.py", '"""' + numbered_lines(20) + '"""\n')
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def run_audit(*all_arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *all_arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def audit_rows(
    checkout: Path, tmp_path: Path, *all_extra_arguments: str
) -> dict[tuple[str, str], dict]:
    rows_path = tmp_path / "rows.jsonl"
    completed = run_audit(str(checkout), "--rows", str(rows_path), *all_extra_arguments)
    assert completed.returncode == 0, completed.stderr
    all_rows = [
        json.loads(each_line) for each_line in rows_path.read_text().splitlines()
    ]
    return {(each_row["path"], each_row["kind"]): each_row for each_row in all_rows}


def test_root_instructions_load_at_session_start_and_carry_when_over_cap(
    checkout: Path, tmp_path: Path
) -> None:
    row_by_key = audit_rows(checkout, tmp_path)
    agents_row = row_by_key[("AGENTS.md", "instructions")]
    assert agents_row["trigger"] == "session-start"
    assert agents_row["loader"] == "@import from CLAUDE.md"
    assert agents_row["lines"] == 30
    assert agents_row["depth_mode"] == "carries"
    assert row_by_key[("CLAUDE.md", "instructions")]["depth_mode"] == "lean"


def test_nested_empty_instructions_load_on_folder_enter_as_empty(
    checkout: Path, tmp_path: Path
) -> None:
    nested_row = audit_rows(checkout, tmp_path)[("nested/CLAUDE.md", "instructions")]
    assert nested_row["trigger"] == "folder-enter"
    assert nested_row["depth_mode"] == "empty"


def test_import_loads_with_importer_and_its_links_follow_on_demand(
    checkout: Path, tmp_path: Path
) -> None:
    row_by_key = audit_rows(checkout, tmp_path)
    assert row_by_key[("docs/shared.md", "import")]["trigger"] == "session-start"
    assert row_by_key[("docs/shared.md", "import")]["depth_mode"] == "points"
    deep_row = row_by_key[("docs/deep.md", "linked-doc")]
    deeper_row = row_by_key[("docs/deeper.md", "linked-doc")]
    assert (deep_row["trigger"], deep_row["depth_mode"], deep_row["note"]) == (
        "on-link",
        "reference",
        "link depth 1",
    )
    assert deeper_row["note"] == "link depth 2"


def test_rule_with_paths_loads_on_path_match_and_plain_rule_at_session_start(
    checkout: Path, tmp_path: Path
) -> None:
    row_by_key = audit_rows(checkout, tmp_path)
    assert row_by_key[(".claude/rules/api.md", "rule")]["trigger"] == "path-match"
    assert (
        row_by_key[(".claude/rules/general.md", "rule")]["trigger"] == "session-start"
    )


def test_skill_yields_listing_body_and_reference_rows(
    checkout: Path, tmp_path: Path
) -> None:
    row_by_key = audit_rows(checkout, tmp_path)
    description_row = row_by_key[(".claude/skills/demo/SKILL.md", "skill-description")]
    body_row = row_by_key[(".claude/skills/demo/SKILL.md", "skill-body")]
    reference_row = row_by_key[
        (".claude/skills/demo/references/guide.md", "skill-reference")
    ]
    assert (description_row["trigger"], description_row["depth_mode"]) == (
        "session-start",
        "points",
    )
    assert (body_row["trigger"], body_row["depth_mode"]) == ("skill-invoke", "carries")
    assert reference_row["trigger"] == "on-link"


def test_disabled_skill_has_no_listing_and_fixture_skill_is_skipped(
    checkout: Path, tmp_path: Path
) -> None:
    row_by_key = audit_rows(checkout, tmp_path)
    assert (".claude/skills/quiet/SKILL.md", "skill-description") not in row_by_key
    assert (".claude/skills/quiet/SKILL.md", "skill-body") in row_by_key
    assert not any(
        each_path.startswith("tests/") and each_kind.startswith("skill")
        for each_path, each_kind in row_by_key
    )


def test_module_docstring_loads_on_file_open_and_carries_over_cap(
    checkout: Path, tmp_path: Path
) -> None:
    docstring_row = audit_rows(checkout, tmp_path)[("tool.py", "docstring")]
    assert (
        docstring_row["trigger"],
        docstring_row["depth_mode"],
        docstring_row["cap"],
    ) == ("file-open", "carries", 15)


def test_saved_hook_text_counts_at_session_start(
    checkout: Path, tmp_path: Path
) -> None:
    hook_text_file = tmp_path / "hook-banner.txt"
    hook_text_file.write_text(numbered_lines(3), encoding="utf-8")
    row_by_key = audit_rows(
        checkout, tmp_path, "--session-start-text", str(hook_text_file)
    )
    hook_row = row_by_key[("hook-banner.txt", "hook-text")]
    assert (hook_row["trigger"], hook_row["lines"], hook_row["depth_mode"]) == (
        "session-start",
        3,
        "lean",
    )


def test_report_lists_each_cleanup_section(checkout: Path) -> None:
    completed = run_audit(str(checkout))
    assert completed.returncode == 0, completed.stderr
    carries_section, _, after_carries = completed.stdout.partition(
        "## Empty instruction stubs"
    )
    stubs_section, _, split_section = after_carries.partition("## Long skills to split")
    assert "| AGENTS.md | instructions | session-start | 30 | 20 |" in carries_section
    assert "| tool.py | docstring | file-open | 20 | 15 |" in carries_section
    assert "SKILL.md" not in carries_section
    assert stubs_section.strip() == "- nested/CLAUDE.md (instructions)"
    assert (
        "| .claude/skills/demo/SKILL.md | 254 | 200 |"
        in split_section.split("\n", 3)[3]
    )


def test_command_option_is_gone_and_text_file_must_exist(
    checkout: Path, tmp_path: Path
) -> None:
    rejected = run_audit(str(checkout), "--session-start-command", "echo hi")
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr
    missing = run_audit(
        str(checkout), "--session-start-text", str(tmp_path / "absent.txt")
    )
    assert missing.returncode == 2
    assert "file not found" in missing.stderr


def test_folder_outside_git_is_refused(tmp_path: Path) -> None:
    completed = run_audit(str(tmp_path))
    assert completed.returncode == 2
    assert "not a git checkout" in completed.stderr
