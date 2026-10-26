"""Tests that a number bound to a descriptive name passes the magic-value check.

A value used once can stay in its function when a name explains it. A
number inside a larger expression still needs a name of its own.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_enforcer_module() -> ModuleType:
    module_path = Path(__file__).parent / "code_rules_enforcer.py"
    specification = importlib.util.spec_from_file_location(
        "code_rules_enforcer_for_named_assignment_tests",
        module_path,
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


code_rules_enforcer = _load_enforcer_module()

PRODUCTION_FILE_PATH = "packages/claude-dev-env/scripts/retry_timing.py"


def _magic_issues_for(function_body_line: str) -> list[str]:
    source = f"def backoff_seconds(attempt: int) -> float:\n    {function_body_line}\n    return attempt\n"
    return code_rules_enforcer.check_magic_values(source, PRODUCTION_FILE_PATH)


def test_should_pass_a_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for("retry_backoff_factor = 2.5") == []


def test_should_pass_an_annotated_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for("retry_backoff_factor: float = 2.5") == []


def test_should_pass_a_negative_number_bound_to_a_local_name() -> None:
    assert _magic_issues_for("lowest_offset = -40") == []


def test_should_flag_a_number_inside_an_expression() -> None:
    assert _magic_issues_for("backoff = attempt * 2.5") == [
        "Line 2: Magic value 2.5 - extract to named constant"
    ]


def test_should_flag_a_number_passed_as_an_argument() -> None:
    assert _magic_issues_for("wait_for(attempt, 2.5)") == [
        "Line 2: Magic value 2.5 - extract to named constant"
    ]


def test_should_flag_a_number_in_a_comparison_assignment() -> None:
    assert _magic_issues_for("is_slow = attempt > 40") == [
        "Line 2: Magic value 40 - extract to named constant"
    ]
