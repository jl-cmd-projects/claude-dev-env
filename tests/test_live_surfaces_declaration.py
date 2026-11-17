"""The repository's declared live surfaces give the tier each kind of path should get."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIRECTORY = REPOSITORY_ROOT / "packages" / "claude-dev-env" / "hooks"
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking.evidence_tier import (
    EvidenceTier,
    TierCause,
    choose_tier,
    declared_live_surface_globs,
)

SURFACES_FILE_PATH = REPOSITORY_ROOT / ".claude" / "live-surfaces.txt"


def _declared_globs() -> tuple[str, ...]:
    all_globs = declared_live_surface_globs(
        SURFACES_FILE_PATH.read_text(encoding="utf-8")
    )
    assert all_globs is not None
    return all_globs


@pytest.mark.parametrize(
    "live_path",
    [
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "packages/claude-dev-env/.claude/skills",
        "packages/claude-dev-env/.claude/agents",
        "packages/claude-dev-env/hooks/git-hooks/pre_push.py",
        "packages/claude-dev-env/hooks/git-hooks/pull_request_handoff.py",
        "packages/claude-dev-env/_shared/pr-loop/scripts/check_bugbot_ci.py",
        "packages/claude-dev-env/hooks/blocking/pull_request_proof.py",
        "packages/claude-dev-env/hooks/blocking/followup_pr_dedupe.py",
        "packages/claude-dev-env/hooks/advisory/pr_done_reminder.py",
        "packages/claude-dev-env/hooks/hooks_constants/gh_api_budget.py",
        "packages/claude-dev-env/hooks/routing/usage_pace.py",
        "packages/claude-dev-env/bin/cde.mjs",
    ],
)
def test_declared_surfaces_should_make_paths_a_test_cannot_reproduce_live(
    live_path: str,
) -> None:
    assert choose_tier([live_path], _declared_globs()).cause is TierCause.LIVE_SURFACE


@pytest.mark.parametrize(
    "path",
    [
        "packages/claude-dev-env/hooks/advisory/owned_pr_review_loop.py",
        "packages/claude-dev-env/hooks/blocking/evidence_tier.py",
        "packages/claude-dev-env/scripts/cde_lint.py",
    ],
)
def test_declared_surfaces_should_leave_other_code_on_the_checked_tier(
    path: str,
) -> None:
    assert choose_tier([path], _declared_globs()).tier is EvidenceTier.CHECKED


@pytest.mark.parametrize(
    "test_path",
    [
        "packages/claude-dev-env/bin/cde.test.mjs",
        "packages/claude-dev-env/_shared/pr-loop/scripts/tests/test_check_bugbot_ci.py",
        "packages/claude-dev-env/hooks/git-hooks/test_config.py",
    ],
)
def test_declared_surfaces_should_leave_tests_under_a_declared_folder_off_the_live_tier(
    test_path: str,
) -> None:
    assert choose_tier([test_path], _declared_globs()).tier is EvidenceTier.NONE


def test_each_declared_path_without_glob_characters_should_exist() -> None:
    all_plain_paths = [
        each_glob
        for each_glob in _declared_globs()
        if not any(each_character in each_glob for each_character in "*?[")
    ]
    all_missing_paths = [
        each_path
        for each_path in all_plain_paths
        if not (REPOSITORY_ROOT / each_path).exists()
    ]
    assert all_missing_paths == []
