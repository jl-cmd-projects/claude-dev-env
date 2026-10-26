"""Behavior tests for the code_rules_magic_values check module.

A diagram-first docstring may carry a bare number on an illustrative row
(``at line 2``). That number is prose, not a code literal, so the magic-value
check skips docstring rows while still flagging a real magic number in an
actual code statement.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BLOCKING_DIRECTORY = str(Path(__file__).resolve().parent)
_HOOKS_DIRECTORY = str(Path(__file__).resolve().parent.parent)
if _BLOCKING_DIRECTORY not in sys.path:
    sys.path.insert(0, _BLOCKING_DIRECTORY)
if _HOOKS_DIRECTORY not in sys.path:
    sys.path.insert(0, _HOOKS_DIRECTORY)

from code_rules_magic_values import check_magic_values  # noqa: E402

PRODUCTION_FILE_PATH = "packages/app/rendering.py"


def test_magic_value_check_skips_bare_number_inside_docstring_illustration() -> None:
    source = (
        "def summarize(record):\n"
        '    """Summarize how a run ended.\n'
        "\n"
        "    A finished run shows a clean outcome::\n"
        "\n"
        "        marked in-flight at row 2\n"
        '    """\n'
        "    return record\n"
    )
    issues = check_magic_values(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"Expected no magic-value issue on an illustrative row, got: {issues}"


def test_magic_value_check_still_flags_real_magic_number_in_code_statement() -> None:
    source = (
        "def summarize(record):\n"
        '    """Summarize how a run ended.\n'
        "\n"
        "        marked in-flight at row 2\n"
        '    """\n'
        "    threshold = record.score * 42\n"
        "    return threshold\n"
    )
    issues = check_magic_values(source, PRODUCTION_FILE_PATH)
    assert any(issue.endswith("Magic value 42 - extract to named constant") for issue in issues), (
        f"Expected the real magic number 42 to stay flagged, got: {issues}"
    )


def _magic_issues_for_function_line(function_body_line: str) -> list[str]:
    source = f"def backoff_seconds(attempt: int) -> float:\n    {function_body_line}\n    return attempt\n"
    return check_magic_values(source, PRODUCTION_FILE_PATH)


def test_should_pass_a_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for_function_line("retry_backoff_factor = 2.5") == []


def test_should_pass_an_annotated_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for_function_line("timeout_seconds: int | None = 30") == []


def test_should_pass_a_named_number_with_a_trailing_comment() -> None:
    assert _magic_issues_for_function_line("timeout = 30  # seconds") == []


def test_should_pass_a_negative_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for_function_line("lowest_offset = -40") == []


def test_should_flag_a_number_inside_an_expression() -> None:
    assert _magic_issues_for_function_line("backoff = attempt * 2.5") == [
        "Line 2: Magic value 2.5 - extract to named constant"
    ]


def test_should_flag_a_number_in_a_comparison_assignment() -> None:
    assert _magic_issues_for_function_line("is_slow = attempt > 40") == [
        "Line 2: Magic value 40 - extract to named constant"
    ]


def test_should_flag_a_keyword_argument_on_its_own_line() -> None:
    source = "def backoff_seconds(attempt: int) -> float:\n    wait_for(\n        attempt,\n        timeout=30\n    )\n    return attempt\n"
    assert check_magic_values(source, PRODUCTION_FILE_PATH) == [
        "Line 4: Magic value 30 - extract to named constant"
    ]


def test_should_flag_a_module_level_binding_after_a_function() -> None:
    source = "def backoff_seconds(attempt: int) -> float:\n    return attempt\nretry_limit = 30\n"
    assert check_magic_values(source, PRODUCTION_FILE_PATH) == [
        "Line 3: Magic value 30 - extract to named constant"
    ]


def test_should_pass_a_positive_signed_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for_function_line("lowest_offset = +40") == []


def test_should_flag_a_number_sharing_a_line_with_a_named_binding() -> None:
    assert _magic_issues_for_function_line("limit = 5; scaled = attempt * 99") == [
        "Line 2: Magic value 5 - extract to named constant"
    ]


def test_should_flag_a_condition_number_beside_a_named_binding() -> None:
    assert _magic_issues_for_function_line("if attempt > 99: limit = 40") == [
        "Line 2: Magic value 99 - extract to named constant"
    ]
