import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
sys.path[:0] = [
    str(flow_directory),
    str(flow_directory.parent / "features-start-with-an-eval"),
    str(flow_directory.parents[2] / "packages" / "claude-dev-env" / "scripts"),
]

import pytest

import run
from run import _summary


def test_summary_counts_passes_and_errors() -> None:
    rows = [
        {"tags": ["group", "rule"], "grade": {"followed": 1, "opened_guide": 1}},
        {"tags": ["group", "rule"], "grade": {"followed": 0, "opened_guide": 0}},
    ]

    summary = _summary(rows, 1)

    assert "followed 1/2" in summary
    assert "group 1/2" in summary
    assert "opened a guide 1/2" in summary
    assert "errors 1" in summary


def test_main_refuses_an_unknown_case_id_with_a_usage_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--variant", "index", "--cases", "w02,zz9"])

    assert run.main() == 2
    assert "unknown case ids: zz9" in caplog.text


def test_main_refuses_an_unknown_variant_with_a_usage_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--variant", "indx"])

    assert run.main() == 2
    assert "unknown variant: indx" in caplog.text
