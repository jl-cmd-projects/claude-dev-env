"""Behavioral tests for shared-tree directory resolution."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import claude_account_profile
import shared_tree_paths
from dev_env_scripts_constants.grok_worker_constants import (
    CLAUDE_CONFIG_DIR_ENV_VAR,
    PROCESS_TREE_DIRECTORY_NAME,
    PROCESS_TREE_KILL_MODULE_FILENAME,
    SCRIPTS_DIRECTORY_NAME,
    SHARED_PACKAGE_DIRECTORY_NAME,
)
from dev_env_scripts_constants.shared_tree_constants import (
    ADVISOR_DIRECTORY_NAME,
    TIER_MODEL_IDS_MODULE_FILENAME,
)


def _build_junction_scripts_layout(
    tmp_path: Path, create_directory_link: Callable[..., None]
) -> Path:
    linked_scripts_directory = tmp_path / "target" / SCRIPTS_DIRECTORY_NAME
    linked_scripts_directory.mkdir(parents=True)
    (linked_scripts_directory / "runner.py").write_text("", encoding="utf-8")
    managed_root = tmp_path / "root"
    managed_root.mkdir()
    create_directory_link(
        from_link=managed_root / SCRIPTS_DIRECTORY_NAME,
        to_target=linked_scripts_directory,
    )
    return managed_root / SCRIPTS_DIRECTORY_NAME / "runner.py"


def _write_process_tree_kill_stub(from_root: Path) -> Path:
    scripts_directory = (
        from_root
        / SHARED_PACKAGE_DIRECTORY_NAME
        / PROCESS_TREE_DIRECTORY_NAME
        / SCRIPTS_DIRECTORY_NAME
    )
    scripts_directory.mkdir(parents=True)
    (scripts_directory / PROCESS_TREE_KILL_MODULE_FILENAME).write_text(
        "", encoding="utf-8"
    )
    return scripts_directory


def test_junction_scripts_dir_finds_shared_tree_on_unresolved_parent(
    tmp_path: Path, create_directory_link: Callable[..., None],
) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    expected_scripts_directory = _write_process_tree_kill_stub(tmp_path / "root")
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_process_tree_scripts_directory(
            module_file, all_environment={}
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory


def test_resolved_parent_is_used_when_link_side_has_no_shared_tree(
    tmp_path: Path, create_directory_link: Callable[..., None],
) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    expected_scripts_directory = _write_process_tree_kill_stub(tmp_path / "target")
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_process_tree_scripts_directory(
            module_file, all_environment={}
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory


def test_configured_root_is_used_when_neither_parent_holds_the_module(
    tmp_path: Path, create_directory_link: Callable[..., None],
) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    configured_root = tmp_path / "configured"
    expected_scripts_directory = _write_process_tree_kill_stub(configured_root)
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_process_tree_scripts_directory(
            module_file,
            all_environment={
                CLAUDE_CONFIG_DIR_ENV_VAR: str(configured_root)
            },
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory


def test_unresolved_parent_wins_when_configured_root_also_holds_the_module(
    tmp_path: Path, create_directory_link: Callable[..., None],
) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    expected_scripts_directory = _write_process_tree_kill_stub(tmp_path / "root")
    configured_root = tmp_path / "configured"
    _write_process_tree_kill_stub(configured_root)
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_process_tree_scripts_directory(
            module_file,
            all_environment={
                CLAUDE_CONFIG_DIR_ENV_VAR: str(configured_root)
            },
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory


def test_missing_module_returns_unresolved_candidate(tmp_path: Path, create_directory_link: Callable[..., None]) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    expected_scripts_directory = (
        tmp_path
        / "root"
        / SHARED_PACKAGE_DIRECTORY_NAME
        / PROCESS_TREE_DIRECTORY_NAME
        / SCRIPTS_DIRECTORY_NAME
    )
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_process_tree_scripts_directory(
            module_file, all_environment={}
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory
    assert not (
        expected_scripts_directory / PROCESS_TREE_KILL_MODULE_FILENAME
    ).is_file()


def test_junction_scripts_dir_finds_advisor_scripts_on_unresolved_parent(
    tmp_path: Path, create_directory_link: Callable[..., None],
) -> None:
    module_file = _build_junction_scripts_layout(tmp_path, create_directory_link)
    expected_scripts_directory = (
        tmp_path
        / "root"
        / SHARED_PACKAGE_DIRECTORY_NAME
        / ADVISOR_DIRECTORY_NAME
        / SCRIPTS_DIRECTORY_NAME
    )
    expected_scripts_directory.mkdir(parents=True)
    (expected_scripts_directory / TIER_MODEL_IDS_MODULE_FILENAME).write_text(
        "", encoding="utf-8"
    )
    resolved_scripts_directory = (
        shared_tree_paths.resolve_shared_advisor_scripts_directory(
            module_file, all_environment={}
        )
    )
    assert resolved_scripts_directory == expected_scripts_directory


def test_generalized_resolver_serves_a_deeper_anchor(tmp_path: Path) -> None:
    """A caller three levels under the root resolves its own sub-package.

    This is the shape the pr-loop and codex-review scripts carry, which the
    process-tree wrapper's own anchor of one level cannot reach.
    """
    installed_root = tmp_path / "root"
    module_directory = installed_root / "_shared" / "pr-loop" / "scripts"
    module_directory.mkdir(parents=True)
    module_file = str(module_directory / "run_codex_review.py")
    expected_scripts_directory = (
        installed_root
        / SHARED_PACKAGE_DIRECTORY_NAME
        / PROCESS_TREE_DIRECTORY_NAME
        / SCRIPTS_DIRECTORY_NAME
    )
    expected_scripts_directory.mkdir(parents=True)
    (expected_scripts_directory / PROCESS_TREE_KILL_MODULE_FILENAME).write_text(
        "", encoding="utf-8"
    )
    resolved_scripts_directory = shared_tree_paths.resolve_shared_scripts_directory(
        module_file,
        {},
        PROCESS_TREE_DIRECTORY_NAME,
        PROCESS_TREE_KILL_MODULE_FILENAME,
        3,
    )
    assert resolved_scripts_directory == expected_scripts_directory


@pytest.mark.parametrize("managed_name", (".claude", "profile-a"))
def test_resolved_agents_scripts_find_the_verified_managed_root(
    tmp_path: Path, create_directory_link: Callable[..., None], managed_name: str,
) -> None:
    agents_name = ".agents" if managed_name == ".claude" else f"{managed_name}.agents"
    agents_root = tmp_path / agents_name
    scripts_directory = agents_root / "scripts"
    scripts_directory.mkdir(parents=True)
    module_file = scripts_directory / "runner.py"
    module_file.write_text("", encoding="utf-8")
    managed_root = tmp_path / managed_name
    managed_root.mkdir()
    create_directory_link(from_link=managed_root / "scripts", to_target=scripts_directory)
    expected = _write_process_tree_kill_stub(managed_root)
    resolved_directory = shared_tree_paths.resolve_shared_process_tree_scripts_directory(module_file, {})
    assert resolved_directory == expected


def test_neighboring_managed_root_cannot_supply_a_foreign_shared_tree(tmp_path: Path) -> None:
    agents_root = tmp_path / ".agents"
    scripts_directory = agents_root / "scripts"
    scripts_directory.mkdir(parents=True)
    module_file = scripts_directory / "runner.py"
    module_file.write_text("", encoding="utf-8")
    managed_root = tmp_path / ".claude"
    foreign_scripts = managed_root / "scripts"
    foreign_scripts.mkdir(parents=True)
    _write_process_tree_kill_stub(managed_root)
    resolved_directory = shared_tree_paths.resolve_shared_process_tree_scripts_directory(module_file, {})
    expected = agents_root / "_shared" / "process-tree" / "scripts"
    assert resolved_directory == expected


def test_should_fail_with_the_link_command_output_when_a_link_cannot_be_made(
    tmp_path: Path,
    create_directory_link: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_link(source_path: Path, link_path: Path) -> None:
        raise subprocess.CalledProcessError(1, ["mklink"], b"", b"Access is denied.")

    monkeypatch.setattr(claude_account_profile, "_link_directory", refuse_link)

    with pytest.raises(pytest.fail.Exception) as failure:
        create_directory_link(from_link=tmp_path / "link", to_target=tmp_path)

    assert "Access is denied." in str(failure.value)


def test_should_fail_with_the_os_error_when_a_symlink_cannot_be_made(
    tmp_path: Path,
    create_directory_link: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_link(source_path: Path, link_path: Path) -> None:
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(claude_account_profile, "_link_directory", refuse_link)

    with pytest.raises(pytest.fail.Exception) as failure:
        create_directory_link(from_link=tmp_path / "link", to_target=tmp_path)

    assert "Operation not permitted" in str(failure.value)
