from turn_review_findings import finding_lines

CHANGED_PATH = "src/service.py"


def test_should_read_a_json_finding_on_a_changed_path() -> None:
    review_text = (
        'Review done.\n[{"file": "src/service.py", "line": 208, "summary": "drops the retry"},'
        ' {"file": "src/other.py", "line": 3, "summary": "unchanged file"}]'
    )
    assert finding_lines(review_text, [CHANGED_PATH]) == ["src/service.py:208 drops the retry"]


def test_should_read_a_prose_finding_that_opens_with_a_changed_path() -> None:
    review_text = (
        "- `src/service.py:208` - drops the retry\nThe change at src/service.py:12 is fine."
    )
    assert finding_lines(review_text, [CHANGED_PATH]) == [
        "- `src/service.py:208` - drops the retry"
    ]


def test_should_report_nothing_for_a_review_that_opens_with_none() -> None:
    review_text = "(none)\n- `src/service.py:208` - looked at the retry, it stays"
    assert finding_lines(review_text, [CHANGED_PATH]) == []
