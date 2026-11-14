"""Code quality checks validator.

Implements:
- Check 30: Function too long (max 30 lines of logic), production files only
- Check 31: Nesting too deep (max 2 levels)
- Check 32: File too long (max 400 lines), production files only

The two length caps read production files only. A test module grows with the
surface it covers, and a linear list of assertions is what a reader wants there,
so capping its length pushes a contributor to split a suite for the counter
rather than for the reader. ``magic_value_checks`` short-circuits on the same
category through the same helper.

The function cap counts lines of logic. A docstring is context a reader needs,
so its lines, blank lines and comment-only lines stay out of the count.
"""

import ast
import io
import sys
import tokenize
from pathlib import Path
from typing import List

from .exempt_paths import is_test_file
from .validator_base import Violation, source_text, syntax_tree


MAX_FUNCTION_LINES = 30
MAX_NESTING_DEPTH = 2
MAX_FILE_LINES = 400


def _docstring_line_numbers(tree: ast.AST) -> frozenset[int]:
    """Return each line that a function or class docstring covers."""
    all_docstring_lines: set[int] = set()
    for each_node in ast.walk(tree):
        if not isinstance(each_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first_statement = each_node.body[0]
        if (
            isinstance(first_statement, ast.Expr)
            and isinstance(first_statement.value, ast.Constant)
            and isinstance(first_statement.value.value, str)
        ):
            last_line = first_statement.end_lineno or first_statement.lineno
            all_docstring_lines.update(range(first_statement.lineno, last_line + 1))
    return frozenset(all_docstring_lines)


def _holds_logic(token: tokenize.TokenInfo, all_docstring_lines: frozenset[int]) -> bool:
    """Return True for a token of code: no comment, layout token or docstring."""
    all_layout_token_types = (
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    )
    if token.type in all_layout_token_types:
        return False
    is_docstring = (
        token.type == tokenize.STRING
        and token.start[0] in all_docstring_lines
        and token.end[0] in all_docstring_lines
    )
    return not is_docstring


def _logic_line_numbers(tree: ast.AST, source: str) -> frozenset[int] | None:
    """Return each line that holds code, or None when the source cannot be tokenized.

    ::

        def area(width, height):          -> logic
            '''Return the area.'''        -> docstring, left out
                                          -> blank, left out
            # width times height          -> comment only, left out
            return width * height  # ok   -> logic

    Every line of a string that runs over several lines counts, apart from a
    docstring. Line ends are read the way the parser reads them, so a line
    number here names the same line as a node's ``lineno``.
    """
    all_docstring_lines = _docstring_line_numbers(tree)
    try:
        all_tokens = list(tokenize.generate_tokens(io.StringIO(source, newline=None).readline))
    except (tokenize.TokenError, SyntaxError):
        return None
    return frozenset(
        each_line
        for each_token in all_tokens
        if _holds_logic(each_token, all_docstring_lines)
        for each_line in range(each_token.start[0], each_token.end[0] + 1)
    )


def _logic_line_count(
    node: ast.FunctionDef | ast.AsyncFunctionDef, all_logic_lines: frozenset[int] | None
) -> int:
    """Return how many lines of logic the function holds, its nested definitions included.

    Without a set of logic lines, every line from ``def`` to the last statement counts.
    """
    all_span_lines = range(node.lineno, (node.end_lineno or node.lineno) + 1)
    if all_logic_lines is None:
        return len(all_span_lines)
    return sum(1 for each_line in all_span_lines if each_line in all_logic_lines)


def check_function_length(tree: ast.AST, filename: str, source: str) -> List[Violation]:
    """Flag each production function that holds more than 30 lines of logic.

    ::

        5 lines of logic under a 60-line docstring   -> no finding
        31 lines of logic                            -> "Function 'run' is 31 lines (max 30)"

    The count leaves out the docstring of the function and of each definition
    nested in it, blank lines and comment-only lines. A test file gets no finding.

    Args:
        tree: The parsed module.
        filename: The path the finding names, also read for the test file exemption.
        source: The text the tree was parsed from.

    Returns:
        One violation for each function over the cap, at its ``def`` line.
    """
    if is_test_file(filename):
        return []

    all_logic_lines = _logic_line_numbers(tree, source)
    violations: List[Violation] = []
    for each_node in ast.walk(tree):
        if not isinstance(each_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        length = _logic_line_count(each_node, all_logic_lines)
        if length > MAX_FUNCTION_LINES:
            violations.append(
                Violation(
                    filename,
                    each_node.lineno,
                    f"Function '{each_node.name}' is {length} lines (max {MAX_FUNCTION_LINES})",
                )
            )

    return violations


def check_nesting_depth(tree: ast.AST, filename: str) -> List[Violation]:
    violations: List[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            max_depth = _get_max_nesting_depth(node, 0)
            if max_depth > MAX_NESTING_DEPTH:
                violations.append(
                    Violation(
                        filename,
                        node.lineno,
                        f"Function '{node.name}' has nesting depth {max_depth} (max {MAX_NESTING_DEPTH})",
                    )
                )

    return violations


def _get_max_nesting_depth(node: ast.AST, current_depth: int) -> int:
    max_depth = current_depth

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            child_depth = _get_max_nesting_depth(child, current_depth + 1)
            max_depth = max(max_depth, child_depth)
        else:
            child_depth = _get_max_nesting_depth(child, current_depth)
            max_depth = max(max_depth, child_depth)

    return max_depth


def check_file_length(file_path: Path) -> List[Violation]:
    violations: List[Violation] = []
    filename = str(file_path)

    if is_test_file(filename):
        return violations

    try:
        lines = source_text(file_path).splitlines()
    except Exception as error:
        return [Violation(filename, 0, f"Error reading file: {error}")]

    if len(lines) > MAX_FILE_LINES:
        violations.append(
            Violation(
                filename,
                1,
                f"File is {len(lines)} lines (max {MAX_FILE_LINES}) - consider splitting",
            )
        )

    return violations


def validate_file(file_path: Path) -> List[Violation]:
    violations: List[Violation] = []
    filename = str(file_path)

    violations.extend(check_file_length(file_path))

    try:
        source = source_text(file_path)
        tree = syntax_tree(source)
    except Exception as error:
        return violations + [Violation(filename, 0, f"Error: {error}")]

    violations.extend(check_function_length(tree, filename, source))
    violations.extend(check_nesting_depth(tree, filename))

    return violations


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: code_quality_checks.py <file1.py> [file2.py ...]", file=sys.stderr)
        return 1

    all_violations: List[Violation] = []

    for file_arg in sys.argv[1:]:
        file_path = Path(file_arg)
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            return 1
        all_violations.extend(validate_file(file_path))

    for violation in all_violations:
        print(violation)

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
