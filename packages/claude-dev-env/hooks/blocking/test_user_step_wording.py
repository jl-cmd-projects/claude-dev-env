import string
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
        ("Action required: NO_PROXY must list the new host before the rerun.", "Action required"),
        ("Needs you: Noël has to sign the access form.", "Needs you"),
        ("Action required: No-reply inbox needs a DNS record.", "Action required"),
        ("Action required: **No-reply** inbox needs a DNS record.", "Action required"),
        ("Action required: no later than Friday, rotate the key.", "Action required"),
        ("Needs you:              no later than Friday.", "Needs you"),
        ("Let me know when none of the old sessions are still open.", "Let me know when"),
        ("Tell me when nothing else is running, and I will archive them.", "Tell me when"),
        ("**Action required:** None of these can wait, so approve item 12 today.", "Action required"),
        ("The release is blocked on you - nothing else is holding it.", "blocked on you"),
        ("Action required: no, approve item 12 first.", "Action required"),
        ("Action required: no) approve", "Action required"),
        ("Action required: No. 12 is ready to merge.", "Action required"),
        ("Waiting on you: No. 4 and No. 7.", "Waiting on you"),
        ("Action required: no", "Action required"),
        ("SKIP_NONE needs your value.", "needs your"),
        ("The status__none filter needs your review.", "needs your"),
        ("Nothing*needs you.", "needs you"),
        ("No**needs your approval**.", "needs your"),
        ("It does not*need you*.", "need you"),
        ("This isn't**needs you**", "needs you"),
        ("Nothing changed--and the deploy needs your approval.", "needs your"),
        ("Nothing on this list\rneeds you.", "needs you"),
        ("Action\rrequired: none.", "Action\nrequired"),
        ("Action required:\rnone.", "Action required"),
        ("(Nothing here needs you.)", "needs you"),
        ("|No item needs you|", "needs you"),
        ("-No item needs you.", "needs you"),
        ("Done.Nothing here needs you.", "needs you"),
        ("Done. No" + " " * 238 + "needs you.", "needs you"),
        ("The do-nothing job " + "x " * 114 + "needs your approval.", "needs your"),
        ("A minor" + " x" * 118 + " needs your approval.", "needs your"),
        ("y " * 150 + "and no" + " " * 235 + "needs you.", "needs you"),
        ("1) Nothing failed\n2) PR 12 needs your merge.", "needs your"),
        ("## Nothing failed in CI\nPR 12 needs your merge.", "needs your"),
        ("Nothing on this list\nneeds you.", "needs you"),
        ("Action required: none... except one: merge PR 12.", "Action required"),
        ("Needs you: nothing...merge PR 12 first.", "Needs you"),
        ("Action required: none. Merge item 12 first.", "Action required"),
        ("Needs you:\nnothing except the merge of PR 12", "Needs you"),
        ("Please just say when the demo sessions may be archived.", "say when"),
        ("The fix_never flag needs your review.", "needs your"),
        ("The do-nothing cron job needs your approval to delete.", "needs your"),
        ("The now-or-never deadline needs your approval.", "needs your"),
        ("## What needs you\n\nNothing.", "needs you"),
        ("- [ ] Say when the demo sessions may be archived.", "Say when"),
        ("_Say when_ the demo sessions may be archived.", "Say when"),
        ("(Say when the demo sessions may be archived.)", "Say when"),
        ("Update the minor " + "z" * 235 + " needs your approval.", "needs your"),
        ("Tie the knot " + "z" * 76 + " " + "y" * 76 + " " + "x" * 81 + " needs your approval.", "needs your"),
        ("No-reply inbox needs your DNS record.", "needs your"),
        ("**No**-reply inbox needs your DNS record.", "needs your"),
        ("The do-**nothing** job needs your approval.", "needs your"),
        ("The **nothing**-burger job needs your approval.", "needs your"),
        ("The yes-and-no question needs your answer.", "needs your"),
        ("The yes-**but**-no reply needs your review.", "needs your"),
        ("Action\nrequired: none.", "Action\nrequired"),
        ("NO_PROXY needs your value before the rerun.", "needs your"),
        ("The docs pull request _needs your_ merge.", "needs your"),
        ("__Action required__: rotate the deploy key.", "Action required"),
        ("Nothing on this list\u2028needs you.", "needs you"),
        ("Action\u2028required: none.", "Action\u2028required"),
        ("Done.\u2028> Two items need you.", "need you"),
        ("Status\u2028~~~\u2028Item 12 needs your merge.\u2028~~~", "needs your"),
        ("Status\x0b<div>\x0bItem 12 needs your merge.", "needs your"),
        ("Action required: none.\u2028Merge item 12 first.", "Action required"),
        ("Action required:\x0cnone.", "Action required"),
        ("Item 5 is ready\x85no later than Friday it needs your merge.", "needs your"),
        ("The deploy did not start because api`/`web needs your token.", "needs your"),
        ("It is not a`x`b c that needs your merge.", "needs your"),
        ("It isn't a`x`b c that needs your merge.", "needs your"),
        ("Action required: none. `run merge 12`", "Action required"),
        ("**Action required:** none `run merge 12`", "Action required"),
        ("Action required: none.\ufffc", "Action required"),
        ("Action required `now`: none.", "Action required"),
        ("No`-reply` inbox needs your record.", "needs your"),
        ("Plea\u017fe say when the demo sessions may be archived.", "say when"),
        ("Ju\u017ft say when the demo sessions may be archived.", "say when"),
        ("\ufeffSay when the demo sessions may be archived.", "Say when"),
        ("\u2022 Say when the demo sessions may be archived.", "Say when"),
        ("(Please say when the demo sessions may be archived.)", "say when"),
        ("**Please** say when the demo sessions may be archived.", "say when"),
        ("Not`-`e PR 5 needs your merge.", "needs your"),
        ("Item 5 needs `the merge command` your run.", "needs   your"),
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
        "**Nothing** here needs you.",
        "_Nothing_ here needs you.",
        "_No open item_ needs you.",
        "- [ ] No open item needs you.",
        "| No item needs you |",
        "It has never been blocked on you.",
        "This is not something that's waiting on you.",
        "y " * 150 + "and no" + " " * 234 + "needs you.",
        "alpha nothing " + "x" * 231 + " needs you.",
        "No" + " " * 238 + "needs you.",
        "Action required: none.",
        "The docs say when the token expires.",
        "There are no items that need you.",
        "I have not found anything that needs you.",
        "No step on this long list of six open items is waiting on you.",
        "**Action required:** none.",
        "**Action required**: nothing",
        "Needs you: **none**",
        "Needs you — _n/a_",
        "Action required: no action.",
        "Needs you: nothing.\nBoth builds passed.",
        "- [x] Say when the demo sessions may be archived.",
        "Action required: no action needed.",
        "Action required: none at this time.",
        "Needs you - nothing right now!",
        "- No open item needs you.",
        "## No step needs you",
        "# No action needed",
        "2) No item needs your review.",
        "**No** item needs you.",
        "- There are no items that need you.",
        "Action required: no actions.",
        "This change does **not** need you.",
        "Item 12 is merged **and** no other item needs you.",
        "__Action required__: none.",
        "There were no items that need you.",
        "Neither build needs you.",
        "The runner no longer needs you.",
        "Nothing here needs **you**.",
        "Action **required**: none.",
        "No item is waiting on [you](https://example.com/you).",
        "**1)** No reviewer needs your approval.",
        "Nothing in `deploy.yml` needs you.",
        "This change does not `yet` need you.",
    ],
)
def test_should_find_no_phrase_in_text_that_hands_the_user_nothing(shown_text: str) -> None:
    assert user_step_wording.waiting_phrase(shown_text) is None


@pytest.mark.parametrize(
    ("shown_text", "expected_phrase"),
    [
        ("Pull request 12 needs **your** approval.", "needs **your"),
        ("Pull request 12 needs *your* approval.", "needs *your"),
        ("Pull request 12 **needs** your approval.", "needs** your"),
        ("Three items are waiting on **you**.", "waiting on **you"),
        ("The rollout is blocked on _you_.", "blocked on _you"),
        ("You **still** need to merge pull request 12.", "You **still** need to"),
        ("Let me know **when** the key is set.", "Let me know **when"),
        ("Action **required**: merge pull request 12.", "Action **required"),
        ("Pull request 12 needs [your approval](https://example.com/12).", "needs [your"),
        ("The release is waiting on [you](https://example.com/you).", "waiting on [you"),
        ("It does not a b c needs **you need to merge it.", "you need to"),
    ],
)
def test_should_find_a_phrase_with_emphasis_or_a_link_bracket_between_its_words(
    shown_text: str, expected_phrase: str
) -> None:
    assert user_step_wording.waiting_phrase(shown_text) == expected_phrase


@pytest.mark.parametrize(
    ("shown_text", "expected_phrase"),
    [
        (
            "Pull request 12 [needs](https://example.com/12) your approval.",
            "needs](https://example.com/12) your",
        ),
        (
            "[You](https://example.com/you) need to merge pull request 12.",
            "You](https://example.com/you) need to",
        ),
        (
            "This is for [you](https://example.com/12) to approve.",
            "for [you](https://example.com/12) to approve",
        ),
        (
            "Let me [know](https://example.com/form) when the key is set.",
            "Let me [know](https://example.com/form) when",
        ),
        ("Pull request 12 [**needs**](https://example.com/12) your approval.", "needs**](https://example.com/12) your"),
        ("Pull request 12 **[needs](https://example.com/12)** your approval.", "needs](https://example.com/12)** your"),
        ("Pull request 12 [needs][1] your approval.", "needs][1] your"),
        ("Pull request 12 [needs][] your approval.", "needs][] your"),
        ("Pull request 12 [needs] your approval.", "needs] your"),
        ("The docs **say** when the token expires.", "say** when"),
        ("The docs [say](https://example.com/docs) when the token expires.", "say](https://example.com/docs) when"),
        ("- [x] [Say](https://example.com/form) when the demo may be archived.", "Say](https://example.com/form) when"),
        ("Pull request 12 [needs](" + "a" * 256 + ") your approval.", "needs](" + "a" * 256 + ") your"),
        ("Pull request 12 [needs][" + "a" * 256 + "] your approval.", "needs][" + "a" * 256 + "] your"),
    ],
)
def test_should_find_a_phrase_with_a_link_around_one_of_its_words(
    shown_text: str, expected_phrase: str
) -> None:
    assert user_step_wording.waiting_phrase(shown_text) == expected_phrase


@pytest.mark.parametrize(
    "shown_text",
    [
        'Pull request 12 [needs](https://example.com/12 "the page") your approval.',
        "Pull request 12 [needs](" + "a" * 257 + ") your approval.",
        "Pull request 12 [needs][" + "a" * 257 + "] your approval.",
        "Pull request 12 [needs][the page] your approval.",
        "Pull request 12 [needs](https://example.com/A_(b)) your approval.",
        "Pull request 12 [needs][a[b]] your approval.",
        "Pull request 12 needs](https://example.com/12)your approval.",
    ],
)
def test_should_find_no_phrase_across_a_link_target_or_label_outside_its_stated_form(
    shown_text: str,
) -> None:
    assert user_step_wording.waiting_phrase(shown_text) is None


@pytest.mark.parametrize(
    "shown_text",
    [
        "Done.`x`a No item needs you.",
        "Done:`x`a No item needs you.",
        "Done,`x`a No item needs you.",
        "Done and`x`a No item needs you.",
        "Done.ab`x`a No item needs you.",
        "Done.abc`x`a No item needs you.",
    ],
)
def test_should_hold_a_match_when_a_clause_break_cuts_a_word_that_holds_a_code_span(
    shown_text: str,
) -> None:
    assert user_step_wording.waiting_phrase(shown_text) == "needs you"
    assert user_step_wording.waiting_phrase(shown_text.replace("`x`a", "")) is None


def test_should_hold_a_match_that_a_word_with_a_code_span_touches() -> None:
    assert user_step_wording.waiting_phrase("It isn't a b c d`x`needs you.") == "needs you"
    assert user_step_wording.waiting_phrase("It isn't a b c `x`needs you.") is None


def test_should_skip_a_negated_match_when_only_emphasis_marks_join_a_code_span() -> None:
    assert user_step_wording.waiting_phrase("No **`x`** item needs you.") is None
    assert user_step_wording.waiting_phrase("No **`x`**a item needs you.") == "needs you"


def test_should_read_the_label_form_before_a_joined_code_span() -> None:
    assert user_step_wording.waiting_phrase("a`x`b Action required: none.") is None
    assert user_step_wording.waiting_phrase("a`x`b Nothing here is an action required.") == "action required"


def test_should_read_joined_code_spans_only_in_the_text_a_match_looks_back_over() -> None:
    negated_tail = " nothing here needs you."
    assert user_step_wording.waiting_phrase("y" * 300 + "`x`" + "z" * 20 + negated_tail) == "needs you"
    assert user_step_wording.waiting_phrase("y" * 20 + "`x`" + "z" * 300 + negated_tail) is None


def test_should_skip_a_match_only_when_a_negating_word_leads_it_in_the_same_clause() -> None:
    assert (
        user_step_wording.waiting_phrase_in_prose("Nothing is open. One item needs you.")
        == "needs you"
    )
    assert user_step_wording.waiting_phrase_in_prose("No step here needs you.") is None


def test_should_hold_a_negating_word_with_any_other_character_joined_to_it() -> None:
    all_sentence_frames = {
        "nothing": "{word} here needs you.",
        "none": "{word} of these needs you.",
        "nobody": "{word} here needs you.",
        "no": "{word} open item needs you.",
        "neither": "{word} build needs you.",
        "nor": "{word} this build needs you.",
        "not": "It does {word} need you.",
        "never": "It is {word} blocked on you.",
        "without": "It runs {word} waiting on you.",
    }
    all_joined_characters = [each_character for each_character in string.punctuation + "a0" if each_character not in "*_"]
    all_plain_texts = [each_frame.format(word=each_negator) for each_negator, each_frame in all_sentence_frames.items()]
    assert [user_step_wording.waiting_phrase_in_prose(each_text) for each_text in all_plain_texts] == [None] * len(
        all_plain_texts
    )
    all_joined_texts = [
        each_frame.format(word=each_joined_word)
        for each_negator, each_frame in all_sentence_frames.items()
        for each_character in all_joined_characters
        for each_joined_word in (each_character + each_negator, each_negator + each_character)
    ]
    all_skipped_texts = [
        each_text for each_text in all_joined_texts if user_step_wording.waiting_phrase_in_prose(each_text) is None
    ]
    assert len(all_joined_texts) > len(all_plain_texts) * len(all_joined_characters)
    assert all_skipped_texts == []
    assert user_step_wording.waiting_phrase_in_prose("It isn't waiting on you.") is None
    assert user_step_wording.waiting_phrase_in_prose("It isn't- waiting on you.") == "waiting on you"


@pytest.mark.parametrize("line_end", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_should_hold_every_match_in_a_paragraph_with_an_odd_line_end(line_end: str) -> None:
    assert "a\nb".splitlines() == ("a" + line_end + "b").splitlines()
    all_negated_texts = [
        "Nothing on this list" + line_end + "needs you.",
        "Nothing here needs you." + line_end,
        line_end + "No open item needs you.",
        "Action required: none." + line_end + "Merge item 12 first.",
        "Action required:" + line_end + "none.",
        "The docs" + line_end + "say when the token expires.",
    ]
    all_skipped_texts = [
        each_text for each_text in all_negated_texts if user_step_wording.waiting_phrase_in_prose(each_text) is None
    ]
    assert all_skipped_texts == []
    assert user_step_wording.waiting_phrase("Nothing here needs you.\n\nBoth builds passed." + line_end) is None


def test_should_read_a_long_text_of_negated_phrases_in_linear_time() -> None:
    long_text = "No action needed.\n" * 60000
    started_at = time.perf_counter()
    assert user_step_wording.waiting_phrase_in_prose(long_text) is None
    assert time.perf_counter() - started_at < 5


def test_should_read_a_last_line_of_tildes_with_no_line_end_in_linear_time() -> None:
    started_at = time.perf_counter()
    assert user_step_wording.waiting_phrase("Both builds passed.\n" + "~" * 200000) is None
    assert time.perf_counter() - started_at < 5
    assert user_step_wording.waiting_phrase("~~~~\nTwo items need you.\n~~~~\nBoth builds passed.") is None
    assert user_step_wording.waiting_phrase("~~~ text\nlog line\n~~~\nTwo items need you.") == "need you"


def test_should_leave_code_quotes_and_unclosed_script_openers_out_of_an_html_page() -> None:
    page_markup = "<p>Status</p><code>needs you</code><pre>waiting on you</pre><blockquote>say when</blockquote>"
    assert user_step_wording.html_visible_text(page_markup).split() == ["Status"]
    started_at = time.perf_counter()
    user_step_wording.html_visible_text("<script " * 30000)
    assert time.perf_counter() - started_at < 5


@pytest.mark.parametrize(
    ("page_markup", "expected_phrase"),
    [
        ("<p>Nothing in <code>x</code> needs you.</p>", None),
        ("<p>No item on the <abbr>PR</abbr> list <br>needs you.</p>", "needs you"),
        ("<p>None of the open items\n   needs you.</p>", None),
        ("<p>Nothing failed<br>PR 12 needs your merge</p>", "needs your"),
        ("<title>What needs you</title><template>Two items need you.</template><p>Both builds passed.</p>", None),
        ("<ul><li>Nothing is blocked</li><li>Pull request 12 needs your approval</li></ul>", "needs your"),
        ("<p>Both builds passed.</p></code><p>Two items need you.</p>", "need you"),
        ("<h2>What it needs</h2><p>You can skip this section.</p>", None),
        ("<h2>Action required</h2><p>None of the items below can ship until you approve item 12.</p>", "Action required"),
        ("<table><tr><td>Needs you</td><td>none</td></tr></table>", "Needs you"),
        ("<p>Action required: <b>none</b>.</p>", None),
        ("<p>No<code>-reply</code> inbox needs your record.</p>", "needs your"),
        ("<p>Action required: none.<code>run merge 12</code></p>", "Action required"),
        ("<p>Action required: none.&#x2028;Merge item 12 first.</p>", "Action required"),
        ("<p>Item 5 is ready&#x2028;no later than Friday it needs your merge.</p>", "needs your"),
        ("<p>Item 5 needs <code>the merge command</code> your run.</p>", "needs   your"),
        ("<p>Pull request 12 need<code></code>s your approval.</p>", "needs your"),
        ("<p>Three items ne<code>x</code>ed you.</p>", "need you"),
        ("<p>A<code>x</code>ction required: none.\ufffc</p>", "Action required"),
    ],
)
def test_should_find_the_phrase_in_each_block_of_a_sent_html_page(
    tmp_path: Path, page_markup: str, expected_phrase: str | None
) -> None:
    page_path = tmp_path / "status.html"
    page_path.write_text(page_markup, encoding="utf-8")
    assert user_step_wording.file_waiting_phrase(str(page_path), None) == expected_phrase


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


def test_html_text_blocks_should_mark_each_shown_heading() -> None:
    page_markup = "<h2>Open questions</h2><p>Run <code>x</code> now.</p><script><h3>hidden</h3></script>"
    assert user_step_wording.html_text_blocks(page_markup, "# ") == ["# Open questions", "Run ￼ now."]


def test_html_text_blocks_should_leave_headings_unmarked_with_an_empty_mark() -> None:
    assert user_step_wording.html_text_blocks("<h1>Status</h1><p>Done.</p>", "") == ["Status", "Done."]


def test_sent_file_text_should_read_a_relative_text_file_and_skip_other_suffixes(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_bytes(b"Status: green \xff")
    (tmp_path / "shot.png").write_text("Should I?", encoding="utf-8")
    assert user_step_wording.sent_file_text("notes.md", str(tmp_path)) == "Status: green �"
    assert user_step_wording.sent_file_text("shot.png", str(tmp_path)) is None
    assert user_step_wording.sent_file_text("missing.md", str(tmp_path)) is None


def test_is_html_file_path_should_match_html_suffixes_in_any_case() -> None:
    assert [
        user_step_wording.is_html_file_path(each_path) for each_path in ("a.HTML", "b.htm", "c.md", "d.html.txt")
    ] == [True, True, False, False]


def test_sent_file_location_should_resolve_a_relative_text_file_and_skip_the_rest(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("Status: green", encoding="utf-8")
    (tmp_path / "shot.png").write_text("Should I?", encoding="utf-8")
    (tmp_path / "folder.md").mkdir()
    assert user_step_wording.sent_file_location("notes.md", str(tmp_path)) == tmp_path / "notes.md"
    assert user_step_wording.sent_file_location("shot.png", str(tmp_path)) is None
    assert user_step_wording.sent_file_location("folder.md", str(tmp_path)) is None
    assert user_step_wording.sent_file_location("missing.md", str(tmp_path)) is None


def test_html_text_blocks_should_mark_a_checkbox_with_the_task_box_mark() -> None:
    page_markup = '<ul><li><input type="checkbox"/> Saved?</li><li><input type="text"> Name</li></ul>'
    assert user_step_wording.html_text_blocks(page_markup, "# ", task_box_mark="- [ ] ") == [
        "- [ ]  Saved?",
        "Name",
    ]


def test_html_text_blocks_should_mark_a_summary_label_as_a_heading() -> None:
    page_markup = "<details><summary>Can I use it offline?</summary><p>After a sync.</p></details>"
    assert user_step_wording.html_text_blocks(page_markup, "# ") == ["# Can I use it offline?", "After a sync."]
