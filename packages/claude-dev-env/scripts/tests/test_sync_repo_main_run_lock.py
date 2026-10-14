"""Specifications for Sync-RepoMain skipping while another run of the same repo is live."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "Sync-RepoMain.ps1"
_PWSH = shutil.which("pwsh") or "pwsh"
_SKIPPED_EXIT_CODE = 3
_SUCCESS_EXIT_CODE = 0
_LOCK_READY_TIMEOUT_SECONDS = 20


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
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _mirror_one_commit_behind(root_path: Path) -> Path:
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
        ["git", "clone", "-q", str(remote_path), str(mirror_path)], check=True
    )
    (author_path / "tracked.txt").write_text("new\n", encoding="utf-8")
    _git(author_path, "commit", "-q", "-am", "second")
    _git(author_path, "push", "-q", "origin", "main")
    return mirror_path


def _run_lock_name(mirror_path: Path) -> str:
    path_digest = (
        hashlib.sha256(str(mirror_path).lower().encode("utf-8")).hexdigest().upper()
    )
    return f"Global\\SyncRepoMain-{path_digest}"


def _run_sync(mirror_path: Path, log_path: Path) -> int:
    completed = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-File",
            str(_SCRIPT_PATH),
            "-RepoPath",
            str(mirror_path),
            "-LogPath",
            str(log_path),
        ],
        capture_output=True,
        text=True,
    )
    return completed.returncode


def test_should_skip_without_fetching_while_another_run_holds_the_lock(
    tmp_path: Path,
) -> None:
    mirror_path = _mirror_one_commit_behind(tmp_path)
    old_tip = _git(mirror_path, "rev-parse", "HEAD")
    log_path = tmp_path / "sync.log"
    ready_path = tmp_path / "lock-ready"
    holder_command = (
        f"$lock = [System.Threading.Mutex]::new($true, '{_run_lock_name(mirror_path)}'); "
        f"Set-Content -LiteralPath '{ready_path}' -Value ready; Start-Sleep -Seconds 30"
    )
    holder = subprocess.Popen([_PWSH, "-NoProfile", "-Command", holder_command])
    try:
        deadline = time.monotonic() + _LOCK_READY_TIMEOUT_SECONDS
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        held_exit_code = _run_sync(mirror_path, log_path)
    finally:
        holder.kill()
        holder.wait()

    assert held_exit_code == _SKIPPED_EXIT_CODE
    assert _git(mirror_path, "rev-parse", "HEAD") == old_tip
    assert "still running" in log_path.read_text(encoding="utf-8")

    assert _run_sync(mirror_path, log_path) == _SUCCESS_EXIT_CODE
    assert _git(mirror_path, "rev-parse", "HEAD") != old_tip
