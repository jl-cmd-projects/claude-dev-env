from code_rules_boolean_mustcheck import check_boolean_naming


def test_boolean_assignment_requires_a_prefix() -> None:
    content = "def check() -> None:\n    enabled = True\n"

    assert check_boolean_naming(content, "src/checks.py") == [
        "Line 2: Boolean enabled - prefix with is_/has_/should_/can_/was_/did_"
    ]
