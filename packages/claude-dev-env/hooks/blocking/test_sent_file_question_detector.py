import time

import pytest

import sent_file_question_detector


@pytest.mark.parametrize(
    ("file_text", "expected_question"),
    [
        ("Checks passed. Should I merge it?\n", "Should I merge it?"),
        ("Three dates fit. What release date works best?\n", "What release date works best?"),
        ("The run is done.\n\n- Did you run the tests?\n", "Did you run the tests?"),
        ("- [ ] Should I archive the old branches?\n", "Should I archive the old branches?"),
        (
            "- Did you run the tests?\n- Keep the cache or clear it?\n",
            "Keep the cache or clear it?",
        ),
    ],
)
def test_question_for_user_should_return_the_question_the_text_asks(
    file_text: str, expected_question: str
) -> None:
    assert (
        sent_file_question_detector.question_for_user(file_text, is_html=False) == expected_question
    )


@pytest.mark.parametrize(
    "file_text",
    [
        "The build passed.\n",
        "## Checklist\n\n- Did you run the tests?\n- Did you update the changelog?\n",
        "- [ ] Did you run the tests?\n",
        "Which Python version works best? Python 3.12.\n",
    ],
)
def test_question_for_user_should_return_none_for_text_that_asks_nothing(file_text: str) -> None:
    assert sent_file_question_detector.question_for_user(file_text, is_html=False) is None


@pytest.mark.parametrize(
    "file_text",
    [
        "# T" + " " * 3000 + "x",
        "**a**" + " " * 50000,
        "**a**" + " " * 50000 + "x",
        "## Open" + " " * 50000 + "questions #" + " " * 50000 + "x",
    ],
)
def test_question_for_user_should_read_long_space_runs_in_linear_time(file_text: str) -> None:
    started_at = time.perf_counter()
    sent_file_question_detector.question_for_user(file_text, is_html=False)
    assert time.perf_counter() - started_at < 1


def test_plain_page_text_should_strip_tags_in_one_pass() -> None:
    page_markup = (
        "<h2>Plan</h2><p>Should I <b>merge</b> it?</p>"
        "<script>var x = 'Do you want this?';</script><pre>Can I go?</pre><p>A &amp; B</p>"
    )
    plain_text = sent_file_question_detector.plain_page_text(page_markup)
    assert "# Plan" in plain_text
    assert "Should I merge it?" in plain_text
    assert "Do you want this?" not in plain_text
    assert "Can I go?" not in plain_text
    assert "A & B" in plain_text
    assert (
        sent_file_question_detector.question_for_user(plain_text, is_html=False)
        == "Should I merge it?"
    )


def test_plain_page_text_should_read_unclosed_script_openers_in_linear_time() -> None:
    started_at = time.perf_counter()
    plain_text = sent_file_question_detector.plain_page_text(
        "<p>Should I merge it?</p>" + "<script " * 30000
    )
    assert time.perf_counter() - started_at < 1
    assert "Should I merge it?" in plain_text


@pytest.mark.parametrize(
    "file_text",
    [
        "Q: one?\n" * 20000,
        "word\n" * 100000,
        ("Should I " + "x " * 400 + "go? ") * 300,
    ],
)
def test_question_for_user_should_read_many_units_in_linear_time(file_text: str) -> None:
    started_at = time.perf_counter()
    sent_file_question_detector.question_for_user(file_text, is_html=False)
    assert time.perf_counter() - started_at < 2
