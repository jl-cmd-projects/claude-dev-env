"""Behavior tests for the jobs command line."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from jobs import cli


@pytest.fixture
def jobs_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "jobs.json"
    monkeypatch.setattr(cli, "JOBS_FILE", path)
    return path


def _run(monkeypatch: pytest.MonkeyPatch, *all_arguments: str) -> None:
    monkeypatch.setattr(sys, "argv", ["jobs", *all_arguments])
    cli.main()


def test_list_prints_job_names_and_statuses(
    jobs_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs_file.write_text('[{"name": "nightly", "status": "done"}]')

    _run(monkeypatch, "list")

    assert capsys.readouterr().out == "nightly done\n"


def test_report_prints_each_finished_job_with_its_date(
    jobs_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs_file.write_text(
        json.dumps(
            [
                {
                    "name": "nightly",
                    "status": "done",
                    "finished_at": "2026-10-08T02:00:00+00:00",
                }
            ]
        )
    )

    _run(monkeypatch, "report", "--days", "100000")

    assert capsys.readouterr().out == "2026-10-08 nightly done\n"


def test_cleanup_deletes_old_logs_and_prints_each_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_log = tmp_path / "old.log"
    old_log.write_text("old")
    (tmp_path / "new.log").write_text("new")
    forty_days_ago = time.time() - 40 * 86400
    os.utime(old_log, (forty_days_ago, forty_days_ago))

    _run(monkeypatch, "cleanup", str(tmp_path), "--days", "30")

    assert capsys.readouterr().out == f"deleted {old_log}\n"
    assert not old_log.exists()


def test_download_saves_the_url_to_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_downloads: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        cli.urllib.request,
        "urlretrieve",
        lambda url, path: all_downloads.append((url, path)),
    )
    target_path = tmp_path / "artifact.zip"

    _run(monkeypatch, "download", "https://example.invalid/a.zip", str(target_path))

    assert all_downloads == [("https://example.invalid/a.zip", target_path)]
