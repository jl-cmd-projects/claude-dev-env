"""Tests for check_library_print."""

from __future__ import annotations

from code_rules_enforcer import check_library_print

LIBRARY_FILE_PATH = "shared_utils/web_automation/sample.py"
CLI_FILE_PATH = "shared_utils/web_automation/sample_cli.py"
PRINTING_SOURCE = "def report_status(status_text: str) -> None:\n    print(status_text)\n"


def test_should_flag_print_call_in_library_module() -> None:
    issues = check_library_print(PRINTING_SOURCE, LIBRARY_FILE_PATH)
    assert issues == [
        "Line 2: Library print() - route through logger or accept an explicit stream parameter"
    ]


def test_should_flag_sys_stderr_write_in_library_module() -> None:
    writing_source = "import sys\n\nsys.stderr.write('done')\n"
    issues = check_library_print(writing_source, LIBRARY_FILE_PATH)
    assert issues == ["Line 3: sys.stderr.write - route through logger"]


def test_should_allow_print_call_in_cli_entry_point() -> None:
    assert check_library_print(PRINTING_SOURCE, CLI_FILE_PATH) == []
