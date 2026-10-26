"""Tests for TODO/FIXME detection."""

from pathlib import Path

import pytest

from .todo_checks import check_untracked_todos, main
from .validator_base import Violation


GOOD_TODO_WITH_ISSUE = '''
def process():
    pass
'''

BAD_TODO_WITHOUT_ISSUE = '''
def process():
    pass
'''


class TestUntrackedTodos:
    def test_no_todo_passes(self) -> None:
        violations = check_untracked_todos(GOOD_TODO_WITH_ISSUE, "test.py")
        assert violations == []

    def test_todo_without_issue_fails(self) -> None:
        code = "# TODO: fix this later\ndef foo(): pass"
        violations = check_untracked_todos(code, "test.py")
        assert len(violations) == 1
        assert "TODO" in violations[0].message
        assert "remove it from source code and track the work outside the file" in violations[0].message

    def test_todo_with_issue_passes(self) -> None:
        code = "# TODO #123: fix this later\ndef foo(): pass"
        violations = check_untracked_todos(code, "test.py")
        assert violations == []

    def test_fixme_without_issue_fails(self) -> None:
        code = "# FIXME: broken\ndef foo(): pass"
        violations = check_untracked_todos(code, "test.py")
        assert len(violations) == 1


def test_main_should_report_an_untracked_todo_in_a_named_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source_path = tmp_path / "worker.py"
    source_path.write_text("def run():\n    pass  # TODO tidy up\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["todo_checks", str(source_path)])
    assert main() == 1
    assert capsys.readouterr().out.startswith(f"{source_path}:2:")
