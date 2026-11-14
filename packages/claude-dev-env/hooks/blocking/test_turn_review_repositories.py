import subprocess
import tempfile
from pathlib import Path

import pytest

from turn_review_repositories import _opted_in_repository_roots, _opted_in_repository_slugs


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setattr(tempfile, "tempdir", str(state_directory))
    return home_directory


def checkout(folder: Path, origin_slug: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=folder, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{origin_slug}.git"],
        cwd=folder,
        check=True,
        capture_output=True,
    )
    return folder


def test_should_read_the_listed_slugs_without_letter_case_or_blanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_TURN_REVIEW_REPOSITORIES", " Owner/App , ,owner/LIB,  ")
    assert _opted_in_repository_slugs() == frozenset({"owner/app", "owner/lib"})


def test_should_take_only_a_checkout_whose_origin_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_directory = tmp_path / "workspace"
    listed_checkout = checkout(project_directory / "app", "owner/app")
    checkout(project_directory / "docs", "owner/docs")
    (project_directory / "notes").mkdir()
    (project_directory / "readme.txt").write_text("notes\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_directory))
    assert _opted_in_repository_roots(frozenset({"owner/app"})) == [listed_checkout.resolve()]


def test_should_list_the_project_folder_first_then_its_children_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_directory = checkout(tmp_path / "workspace", "owner/workspace")
    zeta_checkout = checkout(project_directory / "zeta", "owner/zeta")
    alpha_checkout = checkout(project_directory / "alpha", "owner/alpha")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_directory))
    all_slugs = frozenset({"owner/workspace", "owner/zeta", "owner/alpha"})
    assert _opted_in_repository_roots(all_slugs) == [
        project_directory.resolve(),
        alpha_checkout.resolve(),
        zeta_checkout.resolve(),
    ]
