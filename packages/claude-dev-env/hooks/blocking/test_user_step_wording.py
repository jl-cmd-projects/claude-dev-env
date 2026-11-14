import time
from pathlib import Path

import pytest

import user_step_wording


@pytest.mark.parametrize(
    ("shown_text", "expected_phrase"),
    [
        ("The key is set. Two items need you.", "need you"),
        ("## What needs you\n\nThe vault key goes into each environment.", "needs you"),
        ("The docs pull request is green and needs your merge.", "needs your"),
        ("Here is what I need from you today.", "need from you"),
        ("The release is waiting on you.", "waiting on you"),
        ("The deploy waits for your approval.", "waits for your"),
        ("The rollout is blocked on you.", "blocked on you"),
        ("You still need to add the key.", "You still need to"),
        ("You'll need to sign in first.", "You'll need to"),
        ("The pull request is ready for you to merge.", "for you to merge"),
        ("Two demo sessions are running, so say when they may be archived.", "say when"),
        ("Let me know when the key is in place.", "Let me know when"),
        ("Action required: rotate the deploy key.", "Action required"),
        ("The build is not merged; it needs you to approve it.", "needs you"),
        ("It isn't merged yet and needs your approval.", "needs your"),
        ("The pull request is not merged and needs your review.", "needs your"),
        ("The pull request with no failing checks needs your approval.", "needs your"),
        ("Pull request 12 (not urgent) needs your approval.", "needs your"),
        ("- Say when the demo sessions may be archived.", "Say when"),
        ("- Nothing is blocked on the runner\n- Pull request 12 needs your approval", "needs your"),
    ],
)
def test_should_find_the_phrase_that_says_something_waits_on_the_user(
    shown_text: str, expected_phrase: str
) -> None:
    assert user_step_wording.waiting_phrase(shown_text) == expected_phrase


@pytest.mark.parametrize(
    "shown_text",
    [
        "Both builds passed.",
        "Nothing here needs you.",
        "Nothing else is waiting on you.",
        "None of these need you.",
        "This change does not need you.",
        "No action needed.",
        "The label reads `needs you`.",
        "> What needs you?",
        "```\necho 'this needs you'\n```",
        "None of the open items needs you.",
        "Nothing on this list\nneeds you.",
        "Action required: none.",
        "The docs say when the token expires.",
        "There are no items that need you.",
        "I have not found anything that needs you.",
        "No step on this long list of six open items is waiting on you.",
    ],
)
def test_should_find_no_phrase_in_text_that_hands_the_user_nothing(shown_text: str) -> None:
    assert user_step_wording.waiting_phrase(shown_text) is None


def test_should_skip_a_match_only_when_a_negating_word_leads_it_in_the_same_clause() -> None:
    assert (
        user_step_wording.waiting_phrase_in_prose("Nothing is open. One item needs you.")
        == "needs you"
    )
    assert user_step_wording.waiting_phrase_in_prose("No step here needs you.") is None


def test_should_read_a_long_text_of_negated_phrases_in_linear_time() -> None:
    long_text = "No action needed.\n" * 60000
    started_at = time.perf_counter()
    assert user_step_wording.waiting_phrase_in_prose(long_text) is None
    assert time.perf_counter() - started_at < 5


def test_should_leave_code_quotes_and_unclosed_script_openers_out_of_an_html_page() -> None:
    page_markup = "<p>Status</p><code>needs you</code><pre>waiting on you</pre><blockquote>say when</blockquote>"
    assert user_step_wording.waiting_phrase_in_prose(user_step_wording.html_visible_text(page_markup)) is None
    started_at = time.perf_counter()
    user_step_wording.html_visible_text("<script " * 30000)
    assert time.perf_counter() - started_at < 5


@pytest.mark.parametrize(
    ("page_markup", "expected_phrase"),
    [
        ("<p>Nothing in <code>x</code> needs you.</p>", None),
        ("<p>No item on the <abbr>PR</abbr> list <br>needs you.</p>", None),
        ("<title>What needs you</title><template>Two items need you.</template><p>Both builds passed.</p>", None),
        ("<ul><li>Nothing is blocked</li><li>Pull request 12 needs your approval</li></ul>", "needs your"),
        ("<p>Both builds passed.</p></code><p>Two items need you.</p>", "need you"),
    ],
)
def test_should_find_the_phrase_in_the_text_of_an_html_page(page_markup: str, expected_phrase: str | None) -> None:
    assert user_step_wording.waiting_phrase_in_prose(user_step_wording.html_visible_text(page_markup)) == expected_phrase


def test_should_read_a_sent_file_at_the_size_limit_and_skip_one_byte_past_it(tmp_path: Path) -> None:
    phrase_bytes = b"Two items need you."
    size_limit = user_step_wording.MAXIMUM_SENT_FILE_BYTES
    (tmp_path / "at-limit.txt").write_bytes(b" " * (size_limit - len(phrase_bytes)) + phrase_bytes)
    (tmp_path / "past-limit.txt").write_bytes(b" " * (size_limit + 1 - len(phrase_bytes)) + phrase_bytes)
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "at-limit.txt"), None) == "need you"
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "past-limit.txt"), None) is None


def test_should_read_an_html_page_as_its_visible_text() -> None:
    page_markup = "<style>.a{color:red}</style><h2>What needs you</h2><script>var needsYou = 1</script><p>Merge&nbsp;it.</p>"
    visible_text = user_step_wording.html_visible_text(page_markup)
    assert "What needs you" in visible_text
    assert "Merge\xa0it." in visible_text
    assert user_step_wording.html_visible_text("<p>Nothing <b>here</b> needs you.</p>").strip() == "Nothing here needs you."
    assert "color:red" not in visible_text
    assert "needsYou" not in visible_text


@pytest.mark.parametrize(
    ("file_name", "file_text"),
    [
        ("status.md", "## What needs you\n\nAdd the key."),
        ("status.txt", "What needs you: add the key."),
        ("status.html", "<h2>What needs you</h2><p>Add the key.</p>"),
    ],
)
def test_should_find_the_phrase_in_a_sent_text_file(tmp_path: Path, file_name: str, file_text: str) -> None:
    (tmp_path / file_name).write_text(file_text, encoding="utf-8")
    assert user_step_wording.file_waiting_phrase(str(tmp_path / file_name), None) == "needs you"


def test_should_leave_a_markdown_html_block_out_and_read_the_same_markup_in_an_html_file(tmp_path: Path) -> None:
    page_markup = "<div>\nWhat needs you\n</div>"
    (tmp_path / "status.md").write_text(page_markup, encoding="utf-8")
    (tmp_path / "status.html").write_text(page_markup, encoding="utf-8")
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "status.md"), None) is None
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "status.html"), None) == "needs you"


def test_should_read_a_relative_sent_file_from_the_working_directory(tmp_path: Path) -> None:
    (tmp_path / "status.md").write_text("Two items need you.", encoding="utf-8")
    assert user_step_wording.file_waiting_phrase("status.md", str(tmp_path)) == "need you"


def test_should_skip_a_sent_file_that_is_no_text_file_is_too_large_or_is_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "status.png").write_text("Two items need you.", encoding="utf-8")
    (tmp_path / "large.md").write_text("Two items need you. " * 20000, encoding="utf-8")
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "status.png"), None) is None
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "large.md"), None) is None
    assert user_step_wording.file_waiting_phrase(str(tmp_path / "missing.md"), None) is None


def test_should_never_open_a_sent_path_that_is_no_regular_file_or_cannot_be_a_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder_path = tmp_path / "folder.md"
    folder_path.mkdir()
    all_opened_paths: list[Path] = []
    monkeypatch.setattr(Path, "open", lambda opened_path, *all_arguments, **all_options: all_opened_paths.append(opened_path))
    assert user_step_wording.file_waiting_phrase(str(folder_path), None) is None
    assert user_step_wording.file_waiting_phrase("status\x00.md", str(tmp_path)) is None
    assert all_opened_paths == []
