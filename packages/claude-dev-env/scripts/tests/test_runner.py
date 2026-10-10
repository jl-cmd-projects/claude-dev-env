"""Behavior tests for repository-check orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIRECTORY = Path(__file__).resolve().parent
if str(_TESTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIRECTORY))

from repository_checks.config.constants import (
    ALL_CHECK_IDS,
    CHECK_ID_CLAUDE_MD_ORPHANS,
    CHECK_ID_ENV_VAR_DOCUMENTATION,
    CHECK_ID_PACKAGE_INVENTORY,
    CHECK_ID_PYTEST_TESTPATHS,
    CHECK_ID_TRACKED_PERSONAL_DATA,
    CHECK_ID_TRACKED_PRIVATE_TERMS,
    FAILED_CHECK_EXIT_CODE,
    FINDINGS_EXIT_CODE,
)
from repository_checks.runner import run_repository_checks
from repository_policy_test_support import (
    commit_tracked_files,
    initialize_repository,
    run_policy,
    seed_clean_repository,
    write_text,
)


def test_should_fail_closed_when_tracked_paths_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = seed_clean_repository(tmp_path / "repo")

    def fail_tracked_paths(_repository_root: Path) -> tuple[str, ...]:
        raise OSError("git ls-files failed")

    monkeypatch.setattr(
        "repository_checks.tracked_tree.tracked_relative_paths", fail_tracked_paths
    )
    exit_code, stdout_text, _stderr_text = run_policy(repository_root)
    assert exit_code == FAILED_CHECK_EXIT_CODE
    assert "error: rule failed:" in stdout_text


def test_should_emit_stable_sorted_findings(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    initialize_repository(repository_root)
    write_text(
        repository_root / "zeta" / "CLAUDE.md",
        "# zeta\n\n| File | Role |\n|---|---|\n| `missing_zeta.py` | Missing |\n",
    )
    write_text(
        repository_root / "alpha" / "CLAUDE.md",
        "# alpha\n\n| File | Role |\n|---|---|\n| `missing_alpha.py` | Missing |\n",
    )
    commit_tracked_files(repository_root)
    first_exit_code, first_stdout, _first_stderr = run_policy(repository_root)
    _second_exit_code, second_stdout, _second_stderr = run_policy(repository_root)
    assert first_exit_code == FINDINGS_EXIT_CODE
    assert first_stdout == second_stdout
    assert first_stdout.index("alpha/CLAUDE.md") < first_stdout.index("zeta/CLAUDE.md")


def test_should_fail_closed_when_the_private_term_check_cannot_read_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = seed_clean_repository(tmp_path / "repo")

    def fail_private_term_scan(
        _repository_root: Path, _all_tracked_paths: object
    ) -> list[object]:
        raise OSError("tracked file unreadable")

    monkeypatch.setattr(
        "repository_checks.runner.collect_tracked_private_term_findings",
        fail_private_term_scan,
    )
    exit_code, stdout_text, _stderr_text = run_policy(repository_root)
    assert exit_code == FAILED_CHECK_EXIT_CODE
    assert f"error: rule failed: {CHECK_ID_TRACKED_PRIVATE_TERMS}" in stdout_text


_COLLECTOR_NAME_BY_CHECK_ID = {
    CHECK_ID_CLAUDE_MD_ORPHANS: "collect_claude_md_orphan_findings",
    CHECK_ID_ENV_VAR_DOCUMENTATION: "collect_env_var_documentation_findings",
    CHECK_ID_PACKAGE_INVENTORY: "collect_package_inventory_findings",
    CHECK_ID_PYTEST_TESTPATHS: "collect_pytest_testpath_findings",
    CHECK_ID_TRACKED_PERSONAL_DATA: "collect_tracked_secret_findings",
    CHECK_ID_TRACKED_PRIVATE_TERMS: "collect_tracked_private_term_findings",
}


def test_should_name_a_collector_for_every_check_id() -> None:
    assert tuple(_COLLECTOR_NAME_BY_CHECK_ID) == ALL_CHECK_IDS


@pytest.mark.parametrize(
    ("check_id", "collector_name"), sorted(_COLLECTOR_NAME_BY_CHECK_ID.items())
)
def test_should_fail_closed_under_the_check_id_of_the_collector_that_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    check_id: str,
    collector_name: str,
) -> None:
    repository_root = seed_clean_repository(tmp_path / "repo")

    def fail_collector(_repository_root: Path, _all_tracked_paths: object) -> list[object]:
        raise OSError("collector failed")

    monkeypatch.setattr(f"repository_checks.runner.{collector_name}", fail_collector)

    report = run_repository_checks(repository_root)

    assert report.all_failed_check_ids == (check_id,)
