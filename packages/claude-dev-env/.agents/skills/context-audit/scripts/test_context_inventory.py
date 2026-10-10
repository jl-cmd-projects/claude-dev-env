"""Behavior tests for walking a checkout into context rows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

scripts_directory = str(Path(__file__).resolve().parent)
if scripts_directory not in sys.path:
    sys.path.insert(0, scripts_directory)

from context_audit_constants.config.constants import DepthMode, RowKind, Trigger
from context_inventory import ContextInventory, audit_checkout
from context_sources import ContextRow


def _tracked_checkout(root: Path, text_by_relative_path: dict[str, str]) -> Path:
    for each_relative_path, each_text in text_by_relative_path.items():
        path = root / each_relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(each_text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root.resolve()


def _row_by_key(all_rows: list[ContextRow]) -> dict[tuple[str, RowKind], ContextRow]:
    return {(each_row.path, each_row.kind): each_row for each_row in all_rows}


def test_should_mark_installed_rules_global_unless_path_scoped(tmp_path: Path) -> None:
    root = _tracked_checkout(
        tmp_path / "repo",
        {
            "rules/everywhere.md": "Always.\n",
            "rules/scoped.md": "---\npaths:\n  - src/**\n---\nScoped.\n",
        },
    )

    row_by_key = _row_by_key(audit_checkout(root, root / "rules", None, ()))

    everywhere_row = row_by_key[("rules/everywhere.md", RowKind.RULE)]
    scoped_row = row_by_key[("rules/scoped.md", RowKind.RULE)]
    assert (everywhere_row.trigger, everywhere_row.note) == (
        Trigger.SESSION_START,
        "installed rule: loads in every project",
    )
    assert (scoped_row.trigger, scoped_row.note) == (Trigger.PATH_MATCH, "")
    assert everywhere_row.loader == "Claude Code harness, installed rules folder"


def test_should_skip_rule_folders_that_are_not_installed(tmp_path: Path) -> None:
    root = _tracked_checkout(tmp_path / "repo", {"rules/everywhere.md": "Always.\n"})

    assert audit_checkout(root, None, None, ()) == []


def test_should_list_installed_and_plugin_skills_at_session_start(
    tmp_path: Path,
) -> None:
    long_description = "x" * 1600
    root = _tracked_checkout(
        tmp_path / "repo",
        {
            "pack/skills/tidy/SKILL.md": "---\ndescription: Tidy up.\n---\nBody.\n",
            "plugins/kit/skills/wide/SKILL.md": (
                f"---\ndescription: {long_description}\n---\nBody.\n"
            ),
        },
    )

    row_by_key = _row_by_key(audit_checkout(root, None, root / "pack" / "skills", ()))

    installed_row = row_by_key[("pack/skills/tidy/SKILL.md", RowKind.SKILL_DESCRIPTION)]
    plugin_row = row_by_key[
        ("plugins/kit/skills/wide/SKILL.md", RowKind.SKILL_DESCRIPTION)
    ]
    assert installed_row.loader == "skill listing, installed skills folder"
    assert installed_row.trigger == Trigger.SESSION_START
    assert installed_row.depth_mode == DepthMode.POINTS
    assert plugin_row.loader == "skill listing, plugin skills folder"
    assert (plugin_row.bytes, plugin_row.depth_mode) == (1536, DepthMode.CARRIES)
    assert plugin_row.note == (
        "loads when the plugin is installed; listing truncates at 1,536 characters"
    )


def test_should_name_how_codex_and_claude_reach_an_agents_file(tmp_path: Path) -> None:
    root = _tracked_checkout(
        tmp_path / "repo",
        {
            "AGENTS.md": "Root rules.\n",
            "pkg/AGENTS.md": "Package rules.\n",
            "pkg/CLAUDE.md": "Claude rules.\n",
        },
    )

    row_by_key = _row_by_key(ContextInventory(root, None, None).collect(()))

    assert row_by_key[("AGENTS.md", RowKind.INSTRUCTIONS)].loader == (
        "Claude Code native AGENTS.md read; Codex reads it"
    )
    assert row_by_key[("pkg/AGENTS.md", RowKind.INSTRUCTIONS)].loader == (
        "not read by Claude Code (sibling CLAUDE.md, no import); Codex reads it"
    )
    assert row_by_key[("pkg/AGENTS.md", RowKind.INSTRUCTIONS)].trigger == (
        Trigger.FOLDER_ENTER
    )
