"""Tests for check_bare_except — flags except: / except Exception: / except BaseException:.

Per Plan 1c.bare_except_detector / Phase B4: bare exceptions swallow every
error including KeyboardInterrupt and SystemExit. They hide bugs and make
debugging impossible. Production code names the specific exception class
it intends to catch.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_enforcer_module() -> ModuleType:
    module_path = Path(__file__).parent / "code_rules_enforcer.py"
    spec = importlib.util.spec_from_file_location("code_rules_enforcer", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


code_rules_enforcer = _load_enforcer_module()


def check_bare_except(content: str, file_path: str) -> list[str]:
    return code_rules_enforcer.check_bare_except(content, file_path)


PRODUCTION_FILE_PATH = "/project/src/services.py"
TEST_FILE_PATH = "/project/src/test_services.py"
HOOK_INFRASTRUCTURE_PATH = "/home/user/.claude/hooks/blocking/example.py"


def test_should_flag_bare_except() -> None:
    source = "def fetch():\n    try:\n        do_thing()\n    except:\n        pass\n"
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert any("bare except" in each.lower() for each in issues), (
        f"Expected bare except: flagged, got: {issues!r}"
    )


def test_should_flag_except_exception() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception:\n"
        "        pass\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert any("Exception" in each for each in issues), (
        f"Expected 'except Exception:' flagged, got: {issues!r}"
    )


def test_should_flag_except_base_exception() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except BaseException:\n"
        "        pass\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert any("BaseException" in each for each in issues), (
        f"Expected 'except BaseException:' flagged, got: {issues!r}"
    )


def test_should_not_flag_specific_exception() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except ValueError:\n"
        "        pass\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"Specific exception must not be flagged, got: {issues!r}"


def test_should_not_flag_tuple_of_exceptions() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except (ValueError, KeyError):\n"
        "        pass\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"Tuple of exceptions must not be flagged, got: {issues!r}"


def test_should_skip_test_file() -> None:
    source = "try:\n    do_thing()\nexcept:\n    pass\n"
    issues = check_bare_except(source, TEST_FILE_PATH)
    assert issues == [], f"Test files exempt, got: {issues!r}"


def test_should_skip_hook_infrastructure() -> None:
    source = "try:\n    do_thing()\nexcept:\n    pass\n"
    issues = check_bare_except(source, HOOK_INFRASTRUCTURE_PATH)
    assert issues == [], f"Hook infrastructure exempt, got: {issues!r}"


def test_should_handle_syntax_error_gracefully() -> None:
    source = "try:\n  do(\n"
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"Syntax error must yield no issues, got: {issues!r}"


def test_should_include_line_number() -> None:
    source = "def fetch():\n    try:\n        do_thing()\n    except:\n        pass\n"
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert len(issues) >= 1
    assert "Line 4" in issues[0], f"Issue must include line number, got: {issues[0]!r}"


def test_should_accept_except_exception_with_noqa_ble001_and_reason() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception as each_error:  # noqa: BLE001 - the caller must see the error\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"BLE001 allowance with a reason must pass, got: {issues!r}"


def test_should_accept_except_base_exception_with_noqa_ble001_and_reason() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except BaseException:  # noqa: BLE001 - the worker must report every failure\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"BLE001 allowance with a reason must pass, got: {issues!r}"


def test_should_accept_noqa_listing_ble001_after_another_code() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception:  # noqa: E501, BLE001 - the caller must see the error\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert issues == [], f"BLE001 listed with another code must pass, got: {issues!r}"


def test_should_flag_except_exception_with_noqa_ble001_but_no_reason() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception:  # noqa: BLE001\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert len(issues) == 1, f"BLE001 without a reason must be flagged, got: {issues!r}"
    assert "Exception" in issues[0], f"Expected 'except Exception:' flagged, got: {issues[0]!r}"


def test_should_flag_except_exception_with_noqa_for_another_code_only() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception:  # noqa: E722 - the caller must see the error\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert len(issues) == 1, f"A noqa for another code must not allow it, got: {issues!r}"


def test_should_flag_except_exception_when_allowance_sits_on_the_try_line() -> None:
    source = (
        "def fetch():\n"
        "    try:  # noqa: BLE001 - the caller must see the error\n"
        "        do_thing()\n"
        "    except Exception:\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert len(issues) == 1, f"The allowance applies to its own line only, got: {issues!r}"
    assert "Line 4" in issues[0], f"Issue must name the except line, got: {issues[0]!r}"


def test_should_flag_only_the_handler_without_an_allowance() -> None:
    source = (
        "def fetch():\n"
        "    try:\n"
        "        do_thing()\n"
        "    except Exception as each_error:  # noqa: BLE001 - the caller must see the error\n"
        "        raise\n"
        "    except BaseException:\n"
        "        raise\n"
    )
    issues = check_bare_except(source, PRODUCTION_FILE_PATH)
    assert len(issues) == 1, f"Only the unannotated handler must be flagged, got: {issues!r}"
    assert "Line 6" in issues[0], f"Issue must name the unannotated handler, got: {issues[0]!r}"
