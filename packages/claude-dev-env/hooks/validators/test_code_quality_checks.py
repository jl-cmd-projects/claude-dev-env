"""Tests for code quality checks."""

import ast
import tempfile
from pathlib import Path

import pytest

from .code_quality_checks import (
    check_function_length,
    check_nesting_depth,
    check_file_length,
    validate_file,
)
from .validator_base import Violation


GOOD_SHORT_FUNCTION = '''
def process(items):
    result = []
    for item in items:
        if item.active:
            result.append(item)
    return result
'''

BAD_LONG_FUNCTION = '''
def process(items):
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    line9 = 9
    line10 = 10
    line11 = 11
    line12 = 12
    line13 = 13
    line14 = 14
    line15 = 15
    line16 = 16
    line17 = 17
    line18 = 18
    line19 = 19
    line20 = 20
    line21 = 21
    line22 = 22
    line23 = 23
    line24 = 24
    line25 = 25
    line26 = 26
    line27 = 27
    line28 = 28
    line29 = 29
    line30 = 30
    line31 = 31
    return line31
'''

GOOD_SHALLOW_NESTING = '''
def process(items):
    for item in items:
        if item.active:
            result.append(item)
    return result
'''

BAD_DEEP_NESTING = '''
def process(items):
    for item in items:
        if item.active:
            if item.valid:
                if item.enabled:
                    result.append(item)
    return result
'''


class TestFunctionLength:
    def test_short_function_passes(self) -> None:
        tree = ast.parse(GOOD_SHORT_FUNCTION)
        violations = check_function_length(tree, "test.py", GOOD_SHORT_FUNCTION)
        assert violations == []

    def test_long_function_fails(self) -> None:
        tree = ast.parse(BAD_LONG_FUNCTION)
        violations = check_function_length(tree, "test.py", BAD_LONG_FUNCTION)
        assert len(violations) == 1
        assert "30" in violations[0].message or "lines" in violations[0].message.lower()


class TestNestingDepth:
    def test_shallow_nesting_passes(self) -> None:
        tree = ast.parse(GOOD_SHALLOW_NESTING)
        violations = check_nesting_depth(tree, "test.py")
        assert violations == []

    def test_deep_nesting_fails(self) -> None:
        tree = ast.parse(BAD_DEEP_NESTING)
        violations = check_nesting_depth(tree, "test.py")
        assert len(violations) == 1
        assert "nesting" in violations[0].message.lower()


class TestFileLength:
    def test_short_file_passes(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_file:
            temp_file.write("x = 1\n" * 100)
            temp_path = Path(temp_file.name)

        try:
            violations = check_file_length(temp_path)
            assert violations == []
        finally:
            temp_path.unlink()

    def test_long_file_fails(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_file:
            temp_file.write("x = 1\n" * 450)
            temp_path = Path(temp_file.name)

        try:
            violations = check_file_length(temp_path)
            assert len(violations) == 1
            assert "400" in violations[0].message or "lines" in violations[0].message.lower()
        finally:
            temp_path.unlink()


class TestTestFileExemption:
    def test_long_function_in_a_test_file_passes(self) -> None:
        tree = ast.parse(BAD_LONG_FUNCTION)
        violations = check_function_length(
            tree, "packages/app/test_widget.py", BAD_LONG_FUNCTION
        )
        assert violations == []

    def test_long_function_outside_a_test_file_still_fails(self) -> None:
        tree = ast.parse(BAD_LONG_FUNCTION)
        violations = check_function_length(tree, "packages/app/widget.py", BAD_LONG_FUNCTION)
        assert len(violations) == 1

    def test_long_test_file_passes(self, tmp_path: Path) -> None:
        temp_path = tmp_path / "test_widget.py"
        temp_path.write_text("x = 1\n" * 450, encoding="utf-8")
        assert check_file_length(temp_path) == []

    def test_long_conftest_passes(self, tmp_path: Path) -> None:
        temp_path = tmp_path / "conftest.py"
        temp_path.write_text("x = 1\n" * 450, encoding="utf-8")
        assert check_file_length(temp_path) == []


def _docstring_lines(line_count: int) -> list[str]:
    if line_count == 0:
        return []
    all_detail_lines = [f"    Detail line {each_index}." for each_index in range(line_count - 2)]
    return ['    """Summarize the work.', *all_detail_lines, '    """']


def _function_source(logic_line_count: int, docstring_line_count: int = 0) -> str:
    all_assignment_lines = [
        f"    value_{each_index} = {each_index}" for each_index in range(logic_line_count - 2)
    ]
    all_lines = [
        "def process():",
        *_docstring_lines(docstring_line_count),
        *all_assignment_lines,
        "    return 0",
    ]
    return "\n".join(all_lines) + "\n"


def _function_length_messages(source: str) -> list[str]:
    all_violations = check_function_length(ast.parse(source), "packages/app/widget.py", source)
    return [each_violation.message for each_violation in all_violations]


@pytest.fixture
def production_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("production")


class TestFunctionLogicLineCount:
    def test_five_logic_lines_under_a_sixty_line_docstring_pass(
        self, production_directory: Path
    ) -> None:
        production_path = production_directory / "widget.py"
        production_path.write_text(
            _function_source(logic_line_count=5, docstring_line_count=60), encoding="utf-8"
        )
        assert validate_file(production_path) == []

    def test_thirty_one_logic_lines_fail(self, production_directory: Path) -> None:
        production_path = production_directory / "widget.py"
        production_path.write_text(_function_source(logic_line_count=31), encoding="utf-8")
        all_messages = [each_violation.message for each_violation in validate_file(production_path)]
        assert all_messages == ["Function 'process' is 31 lines (max 30)"]

    def test_thirty_logic_lines_pass(self) -> None:
        assert _function_length_messages(_function_source(logic_line_count=30)) == []

    def test_the_message_counts_logic_lines_only(self) -> None:
        source = _function_source(logic_line_count=31, docstring_line_count=60)
        assert _function_length_messages(source) == ["Function 'process' is 31 lines (max 30)"]

    def test_blank_and_comment_only_lines_are_left_out(self) -> None:
        all_padded_lines: list[str] = []
        for each_line in _function_source(logic_line_count=30).splitlines():
            all_padded_lines.extend([each_line, "", "    # a note between two steps"])
        assert _function_length_messages("\n".join(all_padded_lines) + "\n") == []

    def test_a_line_with_code_and_a_trailing_comment_counts(self) -> None:
        all_commented_lines = [
            f"{each_line}  # a note"
            for each_line in _function_source(logic_line_count=31).splitlines()
        ]
        assert _function_length_messages("\n".join(all_commented_lines) + "\n") == [
            "Function 'process' is 31 lines (max 30)"
        ]

    def test_each_line_of_a_multi_line_string_counts(self) -> None:
        all_text_lines = ["first", "", *[f"row {each_index}" for each_index in range(27)]]
        all_lines = [
            "def process():",
            '    text = """' + all_text_lines[0],
            *all_text_lines[1:],
            '    """',
            "    return text",
        ]
        assert _function_length_messages("\n".join(all_lines) + "\n") == [
            "Function 'process' is 32 lines (max 30)"
        ]

    def test_a_nested_function_adds_its_logic_and_leaves_out_its_docstring(self) -> None:
        all_nested_lines = [
            "    def helper():",
            *[f"    {each_line}" for each_line in _docstring_lines(40)],
            "        return 1",
        ]
        all_outer_lines = _function_source(logic_line_count=29).splitlines()
        all_lines = [all_outer_lines[0], *all_nested_lines, *all_outer_lines[1:]]
        assert _function_length_messages("\n".join(all_lines) + "\n") == [
            "Function 'process' is 31 lines (max 30)"
        ]

    def test_mixed_line_endings_keep_each_line_in_place(self) -> None:
        all_lines = _function_source(logic_line_count=31, docstring_line_count=10).splitlines()
        all_line_endings = ("\r\n", "\n", "\r")
        source = "".join(
            each_line + all_line_endings[each_index % len(all_line_endings)]
            for each_index, each_line in enumerate(all_lines)
        )
        assert _function_length_messages(source) == ["Function 'process' is 31 lines (max 30)"]
