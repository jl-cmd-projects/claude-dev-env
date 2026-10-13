"""Behavior tests for the jobs command line."""

import sys
from pathlib import Path

import pytest

fixture_directory = str(Path(__file__).resolve().parents[1])
if fixture_directory not in sys.path:
    sys.path.insert(0, fixture_directory)

from jobs import cli


def test_list_prints_job_names_and_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text('[{"name": "nightly", "status": "done"}]')
    monkeypatch.setattr(cli, "JOBS_FILE", jobs_file)
    monkeypatch.setattr(sys, "argv", ["jobs", "list"])

    cli.main()

    assert capsys.readouterr().out == "nightly done\n"
