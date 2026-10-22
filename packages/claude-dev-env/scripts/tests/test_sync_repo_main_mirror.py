"""Specifications for Sync-RepoMain returning a mirror left on another branch."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "Sync-RepoMain.ps1"
_PWSH = shutil.which("pwsh") or "pwsh"
_SKIPPED_EXIT_CODE = 3
_SUCCESS_EXIT_CODE = 0
_FAILURE_EXIT_CODE = 1


def _git(repository_path: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "-c",
            "user.name=tester",
            "-c",
            "user.email=tester@example.com",
            "-c",
            "core.autocrlf=false",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _mirror_on_feature_branch_behind_remote(
    root_path: Path, should_advance_remote: bool = True
) -> tuple[Path, str, str]:
    remote_path = root_path / "remote.git"
    author_path = root_path / "author"
    mirror_path = root_path / "mirror"
    remote_path.mkdir()
    author_path.mkdir()
    _git(remote_path, "init", "-q", "--bare", "-b", "main")
    _git(author_path, "init", "-q", "-b", "main")
    (author_path / "tracked.txt").write_text("old\n", encoding="utf-8")
    _git(author_path, "add", "-A")
    _git(author_path, "commit", "-q", "-m", "first")
    _git(author_path, "remote", "add", "origin", str(remote_path))
    _git(author_path, "push", "-q", "origin", "main")
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "clone",
            "-q",
            str(remote_path),
            str(mirror_path),
        ],
        check=True,
    )
    _git(mirror_path, "config", "core.autocrlf", "false")
    _git(mirror_path, "switch", "-q", "-c", "feature")
    (mirror_path / "tracked.txt").write_text("feature\n", encoding="utf-8")
    _git(mirror_path, "commit", "-q", "-am", "feature edit")
    feature_tip = _git(mirror_path, "rev-parse", "HEAD")
    if should_advance_remote:
        (author_path / "tracked.txt").write_text("new\n", encoding="utf-8")
        _git(author_path, "commit", "-q", "-am", "second")
        _git(author_path, "push", "-q", "origin", "main")
    remote_tip = _git(author_path, "rev-parse", "HEAD")
    return mirror_path, feature_tip, remote_tip


def _run_sync(mirror_path: Path, log_path: Path, *switches: str) -> int:
    completed = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-File",
            str(_SCRIPT_PATH),
            "-RepoPath",
            str(mirror_path),
            *switches,
            "-LogPath",
            str(log_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode


def test_should_skip_a_feature_branch_checkout_without_mirror(tmp_path: Path) -> None:
    mirror_path, feature_tip, _ = _mirror_on_feature_branch_behind_remote(tmp_path)
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-StashDirty") == _SKIPPED_EXIT_CODE
    assert _git(mirror_path, "branch", "--show-current") == "feature"
    assert _git(mirror_path, "rev-parse", "HEAD") == feature_tip


def test_should_return_a_feature_branch_checkout_to_main_with_mirror(
    tmp_path: Path,
) -> None:
    mirror_path, feature_tip, remote_tip = _mirror_on_feature_branch_behind_remote(
        tmp_path
    )
    log_path = tmp_path / "sync.log"

    assert (
        _run_sync(mirror_path, log_path, "-StashDirty", "-Mirror")
        == _SUCCESS_EXIT_CODE
    )
    assert _git(mirror_path, "branch", "--show-current") == "main"
    assert _git(mirror_path, "rev-parse", "HEAD") == remote_tip
    assert (mirror_path / "tracked.txt").read_text(encoding="utf-8") == "new\n"
    assert _git(mirror_path, "status", "--porcelain") == ""
    assert _git(mirror_path, "rev-parse", "feature") == feature_tip
    assert f"left branch 'feature' at {feature_tip}" in log_path.read_text(
        encoding="utf-8"
    )


def test_should_restore_main_files_when_main_is_already_current(
    tmp_path: Path,
) -> None:
    mirror_path, feature_tip, remote_tip = _mirror_on_feature_branch_behind_remote(
        tmp_path, should_advance_remote=False
    )
    log_path = tmp_path / "sync.log"

    assert (
        _run_sync(mirror_path, log_path, "-StashDirty", "-Mirror")
        == _SUCCESS_EXIT_CODE
    )
    assert _git(mirror_path, "rev-parse", "HEAD") == remote_tip
    assert (mirror_path / "tracked.txt").read_text(encoding="utf-8") == "old\n"
    assert _git(mirror_path, "status", "--porcelain") == ""
    assert f"tree of branch 'feature' at {feature_tip}" in _git(
        mirror_path, "stash", "list"
    )


def test_should_return_to_main_without_stash_dirty(tmp_path: Path) -> None:
    mirror_path, _, remote_tip = _mirror_on_feature_branch_behind_remote(tmp_path)
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _SUCCESS_EXIT_CODE
    assert _git(mirror_path, "rev-parse", "HEAD") == remote_tip
    assert _git(mirror_path, "status", "--porcelain") == ""


def test_should_name_a_detached_head_it_leaves(tmp_path: Path) -> None:
    mirror_path, feature_tip, remote_tip = _mirror_on_feature_branch_behind_remote(
        tmp_path
    )
    _git(mirror_path, "switch", "-q", "--detach", feature_tip)
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _SUCCESS_EXIT_CODE
    assert _git(mirror_path, "rev-parse", "HEAD") == remote_tip
    assert f"left detached HEAD at {feature_tip}" in log_path.read_text(
        encoding="utf-8"
    )


def test_should_stash_a_file_only_the_left_checkout_tracks(tmp_path: Path) -> None:
    mirror_path, _, remote_tip = _mirror_on_feature_branch_behind_remote(tmp_path)
    (mirror_path / "feature-only.txt").write_text("feature only\n", encoding="utf-8")
    _git(mirror_path, "add", "feature-only.txt")
    _git(mirror_path, "commit", "-q", "-m", "feature-only file")
    (mirror_path / "local-note.txt").write_text("untracked note\n", encoding="utf-8")
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _SUCCESS_EXIT_CODE
    assert _git(mirror_path, "rev-parse", "HEAD") == remote_tip
    assert not (mirror_path / "feature-only.txt").exists()
    assert (mirror_path / "local-note.txt").exists()
    assert _git(mirror_path, "status", "--porcelain") == "?? local-note.txt"


def test_should_stash_a_left_file_that_main_ignores(tmp_path: Path) -> None:
    mirror_path, _, _ = _mirror_on_feature_branch_behind_remote(tmp_path)
    (mirror_path / "build.out").write_text("feature build\n", encoding="utf-8")
    _git(mirror_path, "add", "build.out")
    _git(mirror_path, "commit", "-q", "-m", "feature build output")
    (mirror_path / ".git" / "info" / "exclude").write_text(
        "build.out\n", encoding="utf-8"
    )
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _SUCCESS_EXIT_CODE
    assert not (mirror_path / "build.out").exists()
    assert "tree of branch 'feature'" in _git(mirror_path, "stash", "list")


def test_should_put_head_back_when_the_return_cannot_reset(tmp_path: Path) -> None:
    mirror_path, feature_tip, _ = _mirror_on_feature_branch_behind_remote(tmp_path)
    lock_path = mirror_path / ".git" / "index.lock"
    lock_path.write_text("", encoding="utf-8")
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _FAILURE_EXIT_CODE
    assert _git(mirror_path, "branch", "--show-current") == "feature"
    assert _git(mirror_path, "rev-parse", "HEAD") == feature_tip
    assert "HEAD and index are back on branch 'feature'" in log_path.read_text(
        encoding="utf-8"
    )
    lock_path.unlink()
    assert _git(mirror_path, "status", "--porcelain") == ""


def test_should_skip_a_checkout_with_staged_changes(tmp_path: Path) -> None:
    mirror_path, feature_tip, _ = _mirror_on_feature_branch_behind_remote(tmp_path)
    (mirror_path / "tracked.txt").write_text("staged\n", encoding="utf-8")
    _git(mirror_path, "add", "tracked.txt")
    log_path = tmp_path / "sync.log"

    assert _run_sync(mirror_path, log_path, "-Mirror") == _SKIPPED_EXIT_CODE
    assert _git(mirror_path, "branch", "--show-current") == "feature"
    assert _git(mirror_path, "rev-parse", "HEAD") == feature_tip
    assert _git(mirror_path, "diff", "--cached", "--name-only") == "tracked.txt"
