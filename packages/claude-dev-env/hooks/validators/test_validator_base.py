"""Tests for shared validator base types and its shared read and parse."""

import ast
from pathlib import Path

import pytest

from .validator_base import Violation, run_file_validator_cli, source_text, syntax_tree


class TestViolation:
    def test_violation_str_format(self) -> None:
        violation = Violation(file="test.py", line=42, message="Test message")
        assert str(violation) == "test.py:42: Test message"

    def test_violation_is_immutable(self) -> None:
        violation = Violation(file="test.py", line=42, message="Test message")
        with pytest.raises(AttributeError):
            violation.file = "other.py"

    def test_violation_equality(self) -> None:
        v1 = Violation(file="test.py", line=42, message="Test message")
        v2 = Violation(file="test.py", line=42, message="Test message")
        assert v1 == v2

    def test_violation_hashable(self) -> None:
        violation = Violation(file="test.py", line=42, message="Test message")
        violation_set = {violation}
        assert violation in violation_set

def test_source_text_reads_the_file_once_for_repeated_callers(tmp_path: Path) -> None:
    """Two callers asking for the same unchanged file cause one read."""
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    first = source_text(target)
    second = source_text(target)
    assert first == second == "value = 1\n"
    assert source_text.__module__ == "validators.validator_base"


def test_source_text_reads_again_after_the_file_changes(tmp_path: Path) -> None:
    """An edited file is read again rather than served from the cache.

    The cache key carries the modification time and the size, so a rewrite
    between two calls reaches disk a second time.
    """
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    assert source_text(target) == "value = 1\n"
    target.write_text("value = 2\nvalue = 3\n", encoding="utf-8")
    assert source_text(target) == "value = 2\nvalue = 3\n"


def test_source_text_raises_for_a_missing_file(tmp_path: Path) -> None:
    """A caller's own error handling still sees the read failure."""
    with pytest.raises(OSError):
        source_text(tmp_path / "absent.py")


def test_syntax_tree_returns_the_same_tree_for_the_same_source() -> None:
    """One parse serves every caller asking about the same text."""
    source = "def handler() -> int:\n    return 1\n"
    assert syntax_tree(source) is syntax_tree(source)


def test_syntax_tree_parses_what_ast_parse_parses() -> None:
    """The shared parse agrees with a direct ast.parse of the same text."""
    source = "value = 1\n"
    assert ast.dump(syntax_tree(source)) == ast.dump(ast.parse(source))


def test_syntax_tree_raises_syntax_error_for_unparseable_source() -> None:
    """A caller's own SyntaxError branch still fires."""
    with pytest.raises(SyntaxError):
        syntax_tree("def broken(:\n")


def _flag_every_file(file_path: Path) -> list[Violation]:
    return [Violation(file=str(file_path), line=3, message="flagged")]


def test_run_file_validator_cli_should_print_violations_and_fail(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_file_validator_cli(_flag_every_file, ["validator", "a.py", "b.py"])
    assert exit_code == 1
    assert capsys.readouterr().out == "a.py:3: flagged\nb.py:3: flagged\n"


def test_run_file_validator_cli_should_pass_clean_files() -> None:
    assert run_file_validator_cli(lambda file_path: [], ["validator", "a.py"]) == 0


def test_run_file_validator_cli_should_fail_with_no_file_named() -> None:
    assert run_file_validator_cli(_flag_every_file, ["validator"]) == 1
