from code_rules_enforcer import validate_content_for_full_gate


def test_full_gate_reports_boolean_name_violation() -> None:
    content = "def check() -> None:\n    enabled = True\n"

    issues = validate_content_for_full_gate(content, "src/checks.py")

    assert "Line 2: Boolean enabled - prefix with is_/has_/should_/can_/was_/did_" in issues
