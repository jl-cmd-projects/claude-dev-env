from code_rules_imports_logging import check_imports_at_top


def test_import_inside_function_is_reported() -> None:
    content = "import os\n\ndef check() -> None:\n    import sys\n"

    assert check_imports_at_top(content) == [
        "Line 4: Import inside function - move to top of file"
    ]
