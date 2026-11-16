"""Behavior tests for the evidence tier a pull request's changed paths give it."""

import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking.evidence_tier import (
    EvidenceTier,
    TierCause,
    TierChoice,
    choose_tier,
    declared_live_surface_globs,
    first_agent_surface_path,
    is_docs_or_test_path,
)

DECLARED_GLOBS = ("packages/app/docs/rule-guides/", "portal/*_client.py")


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/guide.rst",
        "docs/data/table.json",
        "tests/test_gate.py",
        "src/test_gate.py",
        "src/gate_test.py",
        "web/button.spec.ts",
        "conftest.py",
        "art/logo.png",
    ],
)
def test_is_docs_or_test_path_should_accept_docs_data_and_test_files(path: str) -> None:
    assert is_docs_or_test_path(path)


@pytest.mark.parametrize("path", ["src/gate.py", "data/table.json", "scripts/run.sh"])
def test_is_docs_or_test_path_should_reject_code(path: str) -> None:
    assert not is_docs_or_test_path(path)


def test_choose_tier_should_give_none_when_every_path_is_a_doc_or_a_test() -> None:
    choice = choose_tier(["README.md", "tests/test_gate.py"], DECLARED_GLOBS)
    assert choice == TierChoice(TierCause.ONLY_DOCS_AND_TESTS, None)
    assert choice.tier is EvidenceTier.NONE


def test_choose_tier_should_give_checked_for_code_that_no_declared_glob_names() -> None:
    choice = choose_tier(["README.md", "src/gate.py"], DECLARED_GLOBS)
    assert choice == TierChoice(TierCause.CODE_WITHOUT_LIVE_SURFACE, "src/gate.py")
    assert choice.tier is EvidenceTier.CHECKED


def test_choose_tier_should_give_live_for_code_when_the_base_declares_no_surfaces() -> None:
    choice = choose_tier(["README.md", "src/gate.py"], None)
    assert choice == TierChoice(TierCause.NO_DECLARED_SURFACES, "src/gate.py")
    assert choice.tier is EvidenceTier.LIVE


def test_choose_tier_should_keep_none_for_docs_when_the_base_declares_no_surfaces() -> None:
    assert choose_tier(["README.md"], None).tier is EvidenceTier.NONE


@pytest.mark.parametrize("all_changed_paths", [None, []])
def test_choose_tier_should_give_live_when_the_file_list_is_unread_or_empty(
    all_changed_paths: list[str] | None,
) -> None:
    choice = choose_tier(all_changed_paths, DECLARED_GLOBS)
    assert choice == TierChoice(TierCause.UNREAD_FILE_LIST, None)
    assert choice.tier is EvidenceTier.LIVE


@pytest.mark.parametrize(
    "live_path",
    [
        ".agents/skills/pull-request/SKILL.md",
        ".agents/skills/pull-request/scripts/pull_request.py",
        "packages/app/rules/index.md",
        ".claude/agents/reviewer.md",
        "commands/ship.md",
        "AGENTS.md",
        "packages/app/CLAUDE.md",
        "system-prompts/engineer.xml",
        "packages/app/hooks/hooks.json",
        ".claude/settings.local.json",
        ".github/workflows/ci.yml",
        "web/page.tsx",
        ".claude/live-surfaces.txt",
        "packages/app/docs/rule-guides/proof.md",
        "portal/seller_client.py",
    ],
)
def test_choose_tier_should_give_live_and_name_the_first_live_surface(live_path: str) -> None:
    choice = choose_tier(["README.md", "src/gate.py", live_path], DECLARED_GLOBS)
    assert choice == TierChoice(TierCause.LIVE_SURFACE, live_path)
    assert choice.tier is EvidenceTier.LIVE


def test_choose_tier_should_never_give_none_for_a_doc_that_is_an_agent_surface() -> None:
    assert choose_tier(["skills/x/SKILL.md"], DECLARED_GLOBS).tier is EvidenceTier.LIVE


def test_choose_tier_should_not_count_an_archived_skills_folder_as_an_agent_surface() -> None:
    assert choose_tier(["skills-archived/x/notes.md"], DECLARED_GLOBS).tier is EvidenceTier.NONE


def test_declared_live_surface_globs_should_skip_comments_and_blank_lines() -> None:
    text = "# agent prose\npackages/app/docs/rule-guides/\n\n   \n  # indented comment\nportal/*_client.py  \n"
    assert declared_live_surface_globs(text) == DECLARED_GLOBS


def test_declared_live_surface_globs_should_drop_a_leading_byte_order_mark() -> None:
    assert declared_live_surface_globs("﻿src/\nportal/\n") == ("src/", "portal/")


def test_declared_live_surface_globs_should_give_none_for_text_with_undecodable_bytes() -> None:
    assert declared_live_surface_globs("�� src/\n") is None


@pytest.mark.parametrize(
    ("changed_path", "declared_line"),
    [
        ("src/a.py", "src"),
        ("src/deep/a.py", "src"),
        ("src", "src"),
        ("packages/app/.claude/skills", "packages/app/.claude/skills"),
    ],
)
def test_choose_tier_should_read_a_plain_declared_line_as_a_folder_or_a_file(
    changed_path: str, declared_line: str
) -> None:
    assert choose_tier([changed_path], (declared_line,)) == TierChoice(
        TierCause.LIVE_SURFACE, changed_path
    )


def test_choose_tier_should_not_stretch_a_plain_declared_line_over_a_longer_name() -> None:
    assert choose_tier(["src2/a.py"], ("src",)) == TierChoice(
        TierCause.CODE_WITHOUT_LIVE_SURFACE, "src2/a.py"
    )


def test_first_agent_surface_path_should_name_the_first_agent_surface() -> None:
    all_paths = [
        "src/gate.py",
        "packages/app/docs/rule-guides/proof.md",
        "rules/proof.md",
        "SKILL.md",
    ]
    assert first_agent_surface_path(all_paths) == "rules/proof.md"


def test_first_agent_surface_path_should_ignore_workflows_pages_and_declared_surfaces() -> None:
    all_paths = [
        "src/gate.py",
        ".github/workflows/ci.yml",
        "web/page.html",
        "portal/seller_client.py",
    ]
    assert first_agent_surface_path(all_paths) is None
