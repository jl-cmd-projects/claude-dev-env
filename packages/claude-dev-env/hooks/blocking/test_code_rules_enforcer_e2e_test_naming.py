"""Tests for check_e2e_test_naming."""

from __future__ import annotations

from code_rules_enforcer import check_e2e_test_naming

SPEC_FILE_PATH = "tests/e2e/checkout.spec.ts"
COMPONENT_TEST_FILE_PATH = "src/checkout.test.ts"
ONLINE_TEST_SOURCE = "test('submits the order when online', async () => {});\n"


def test_should_flag_online_word_in_spec_test_name() -> None:
    assert check_e2e_test_naming(ONLINE_TEST_SOURCE, SPEC_FILE_PATH) == [
        "Line 1: Test name contains online/offline - file scope defines this"
    ]


def test_should_allow_spec_test_name_without_network_state() -> None:
    source = "test('submits the order', async () => {});\n"
    assert check_e2e_test_naming(source, SPEC_FILE_PATH) == []


def test_should_skip_file_that_is_not_a_spec() -> None:
    assert check_e2e_test_naming(ONLINE_TEST_SOURCE, COMPONENT_TEST_FILE_PATH) == []
