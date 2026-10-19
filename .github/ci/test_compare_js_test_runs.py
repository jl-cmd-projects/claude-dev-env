"""Checks that the performance comparison keeps coverage and its time limit."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_js_test_runs import main, read_report


def report_text(duration: float) -> str:
    return (
        "\u2714 first case (10ms)\n"
        "\u2714 second case (20ms)\n"
        "\u2139 tests 2\n\u2139 pass 2\n\u2139 fail 0\n"
        "\u2139 cancelled 0\n\u2139 skipped 0\n\u2139 todo 0\n"
        f"\u2139 duration_ms {duration}\n"
    )


@pytest.mark.parametrize(("duration", "exit_code"), [(40, 0), (50, 0), (51, 1), (100, 1)])
def test_cli_enforces_the_duration_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duration: float, exit_code: int
) -> None:
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    before.write_text(report_text(100), encoding="utf-8")
    after.write_text(report_text(duration), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["compare", str(before), str(after)])
    assert main() == exit_code


@pytest.mark.parametrize(
    "report",
    [
        "",
        report_text(1).replace("\u2714 first case (10ms)\n", ""),
        report_text(1).replace("fail 0", "fail 1"),
        report_text(1).replace("cancelled 0", "cancelled 1"),
        report_text(0),
    ],
)
def test_incomplete_or_unsuccessful_reports_fail(tmp_path: Path, report: str) -> None:
    path = tmp_path / "report.log"
    path.write_text(report, encoding="utf-8")
    with pytest.raises(ValueError):
        read_report(path)


def test_a_faster_run_with_different_tests_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    before.write_text(report_text(100), encoding="utf-8")
    after.write_text(report_text(1).replace("second case", "replacement case"), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["compare", str(before), str(after)])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
