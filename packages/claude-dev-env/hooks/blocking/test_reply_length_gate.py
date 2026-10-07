import io
import json
from pathlib import Path

import pytest

import reply_length_gate

REPLY_TOOL_NAME = "mcp__hearthbot__reply"
POST_TOOL_NAME = "mcp__hearthbot__post_message"
SIXTEEN_WORD_SENTENCE = (
    "One two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen."
)
FIFTEEN_WORD_SENTENCE = (
    "One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen."
)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: dict[str, object],
    transcript_path: Path | None = None,
) -> tuple[int, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = reply_length_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_allow_three_short_sentences(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "The fix is in. Tests pass. It ships with the next release."},
    )
    assert (exit_code, stderr_text) == (0, "")


def test_should_allow_a_fifteen_word_sentence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": FIFTEEN_WORD_SENTENCE})
    assert exit_code == 0


def test_should_deny_four_sentences_and_name_the_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "One. Two. Three. Four."},
    )
    assert exit_code == 2
    assert "4 sentences" in stderr_text
    assert "3" in stderr_text


def test_should_deny_a_sixteen_word_sentence_and_name_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": SIXTEEN_WORD_SENTENCE}
    )
    assert exit_code == 2
    assert "16 words" in stderr_text
    assert "15" in stderr_text
    assert "One two three" in stderr_text


def test_should_check_the_project_chat_post_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, POST_TOOL_NAME, {"text": "One. Two. Three. Four."})
    assert exit_code == 2


def test_should_count_each_line_of_a_list_as_a_sentence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "Done:\n- first item\n- second item\n- third item"},
    )
    assert exit_code == 2
    assert "4 sentences" in stderr_text


def test_should_not_count_urls_as_words(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    long_url = "https://example.com/" + "/".join(["segment"] * 20)
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": f"The draft is up at {long_url} for review."},
    )
    assert exit_code == 0


def test_should_not_count_link_targets_as_words(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {
            "text": "Read [the pull request](https://example.com/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p) now."
        },
    )
    assert exit_code == 0


def test_should_not_count_backticked_spans_as_words(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {
            "text": "Run `one two three four five six seven eight nine ten eleven twelve thirteen` now."
        },
    )
    assert exit_code == 0


def test_should_not_count_fenced_blocks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fenced_block = "```\nOne.\nTwo.\nThree.\nFour.\n" + SIXTEEN_WORD_SENTENCE + "\n```"
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": f"Paste this block.\n{fenced_block}"},
    )
    assert exit_code == 0


def test_should_not_split_on_decimal_points(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "Version 4.5 shipped. Speed rose 2.5 times. Nothing else moved."},
    )
    assert exit_code == 0


def test_should_allow_other_tools(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch, capsys, "mcp__other__reply", {"text": "One. Two. Three. Four."}
    )
    assert exit_code == 0


def test_should_allow_a_call_without_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"card": {"blocks": []}})
    assert exit_code == 0


def test_should_allow_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"")))
    assert reply_length_gate.main() == 0


def test_should_deny_a_pr_number_with_no_link_and_name_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "Both land in PR 5256."}
    )
    assert exit_code == 2
    assert "PR 5256" in stderr_text


def test_should_deny_a_bare_hash_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, POST_TOOL_NAME, {"text": "It merged in #4347."}
    )
    assert exit_code == 2
    assert "#4347" in stderr_text


def test_should_allow_a_pr_number_inside_its_link(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "Both land in [PR 5256](https://github.com/owner/repo/pull/5256)."},
    )
    assert (exit_code, stderr_text) == (0, "")


def test_should_allow_a_bare_pull_request_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "Pull request: https://github.com/owner/repo/pull/5256"},
    )
    assert exit_code == 0


def test_should_deny_a_reply_that_says_likely_and_name_the_word(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "The back-test flagged the garland star. It likely flags the call button."},
    )
    assert exit_code == 2
    assert 'Banned word "likely"' in stderr_text


def test_should_allow_the_same_reply_without_the_banned_word(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "The back-test flagged the garland star. It flags the call button in 7 themes."},
    )
    assert (exit_code, stderr_text) == (0, "")


@pytest.mark.parametrize(
    "reply_text",
    ["Really fast.", "A real-world case.", "In   reality it passed.", "ACTUALLY done."],
)
def test_should_deny_default_banned_words_in_any_case_and_spacing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, POST_TOOL_NAME, {"text": reply_text})
    assert exit_code == 2


@pytest.mark.parametrize(
    "reply_text",
    [
        "I realized the cache missed.",
        "Run `actual_count` again.",
        "See https://example.com/likely.",
    ],
)
def test_should_allow_banned_words_inside_longer_words_code_and_urls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text})
    assert exit_code == 0


def test_should_replace_the_defaults_with_the_configured_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config_path = tmp_path / ".claude" / "reply-banned-words.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"banned_words": ["synergy"]}), encoding="utf-8")
    likely_exit_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "It likely passed."}
    )
    synergy_exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "Synergy shipped."}
    )
    assert (likely_exit_code, synergy_exit_code) == (0, 2)
    assert 'Banned word "synergy"' in stderr_text


def test_should_read_the_list_from_the_path_the_environment_names(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config_path = tmp_path / "words.json"
    config_path.write_text(json.dumps({"banned_words": ["basically"]}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_REPLY_BANNED_WORDS_PATH", str(config_path))
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "Basically done."})
    assert exit_code == 2


def test_should_keep_the_defaults_when_the_config_file_is_malformed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config_path = tmp_path / ".claude" / "reply-banned-words.json"
    config_path.parent.mkdir()
    config_path.write_text("{not json", encoding="utf-8")
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "It likely passed."})
    assert exit_code == 2


DECISION_TOOL_NAME = "mcp__hearthbot__ask_decision"


def test_should_deny_a_decision_card_that_hedges_in_an_option(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {
            "question": "Exclude the call button?",
            "context": "Crops show the call button flagged in 7 themes.",
            "options": [
                {"label": "Exclude it", "consequence": "Three themes probably pass."},
                {"label": "Leave it", "consequence": "Three themes keep a warning."},
            ],
            "recommended": 0,
        },
    )
    assert exit_code == 2
    assert '"probably"' in stderr_text


def test_should_allow_a_long_decision_card_with_no_hedge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {
            "question": "Exclude the call button?",
            "context": " ".join([FIFTEEN_WORD_SENTENCE] * 5),
            "options": [
                {"label": "Exclude it", "consequence": SIXTEEN_WORD_SENTENCE},
                {"label": "Leave it", "consequence": "Three themes keep a warning."},
            ],
            "recommended": 0,
        },
    )
    assert (exit_code, stderr_text) == (0, "")


@pytest.mark.parametrize(
    "reply_text",
    ["It maybe passed.", "Perhaps it passed.", "It might be the cache.", "I am not sure it passed."],
)
def test_should_deny_the_hedges_the_default_list_adds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text})
    assert exit_code == 2


def test_should_ignore_a_banned_word_in_a_card_field_that_holds_no_prose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {
            "question": "Exclude the call button?",
            "context": "Crops show the call button flagged in 7 themes.",
            "options": [
                {"id": "maybe", "label": "Exclude it", "consequence": "Seven themes pass."},
                {"id": "leave", "label": "Leave it", "consequence": "Seven themes keep a warning."},
            ],
            "kind": "maybe",
            "recommended": 0,
        },
    )
    assert (exit_code, stderr_text) == (0, "")


@pytest.mark.parametrize(
    "card_field_name",
    ["question", "context", "label", "consequence"],
)
def test_should_deny_a_banned_word_in_each_card_prose_field(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], card_field_name: str
) -> None:
    option = {"label": "Exclude it", "consequence": "Seven themes pass."}
    card: dict[str, object] = {
        "question": "Exclude the call button?",
        "context": "Crops show the call button flagged.",
        "options": [option],
    }
    if card_field_name in option:
        option[card_field_name] = "It maybe passes."
    else:
        card[card_field_name] = "It maybe passes."
    exit_code, stderr_text = run_gate(monkeypatch, capsys, DECISION_TOOL_NAME, card)
    assert exit_code == 2
    assert '"maybe"' in stderr_text


def test_should_apply_the_configured_list_to_decision_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config_path = tmp_path / ".claude" / "reply-banned-words.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"banned_words": ["synergy"]}), encoding="utf-8")
    probably_exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {"question": "Ship it?", "context": "It probably passes."},
    )
    synergy_exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {"question": "Ship it?", "context": "Synergy shipped."},
    )
    assert (probably_exit_code, synergy_exit_code) == (0, 2)
    assert 'Banned word "synergy"' in stderr_text


QUOTED_COLON_SENTENCE = "That second reading matters: one message added 6.7k to Messages."


def test_should_deny_the_quoted_mid_sentence_colon(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, POST_TOOL_NAME, {"text": QUOTED_COLON_SENTENCE}
    )
    assert exit_code == 2
    assert "colon" in stderr_text


@pytest.mark.parametrize(
    "allowed_text",
    [
        "That second reading matters. One message added 6.7k to Messages.",
        "Two checks failed:\n- lint\n- types",
        "It fired at 9:47 today.",
        "The call `a: int` passed.",
        "See https://example.com/a: b for it.",
        "Both land in [PR 5256](https://github.com/owner/repo/pull/5256).",
        "```\nflag: x\n```",
    ],
)
def test_should_allow_a_colon_that_introduces_a_list_or_sits_in_a_span(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], allowed_text: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": allowed_text})
    assert (exit_code, stderr_text) == (0, "")


def test_should_deny_an_em_dash_and_allow_one_in_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    denied_code, denied_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "The fix \u2014 a rename \u2014 is in."}
    )
    allowed_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "The fix uses `\u2014` in a label."}
    )
    assert (denied_code, allowed_code) == (2, 0)
    assert "em dash" in denied_text


WIDGET_TOOL_NAME = "mcp__hearthbot__post_widget"
TWO_SENTENCE_REPLY = "The deploy stopped on a missing file. The page shows each step."


def write_transcript(transcript_path: Path, all_entries: list[dict[str, object]]) -> Path:
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries), encoding="utf-8"
    )
    return transcript_path


def prompt_entry(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_call_entry(tool_name: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": tool_name, "input": {}}]},
    }


def turn_mode_off(tmp_path: Path) -> None:
    switch_path = tmp_path / ".claude" / "visual-reply-mode.json"
    switch_path.parent.mkdir(exist_ok=True)
    switch_path.write_text('{"enabled": false}', encoding="utf-8")


def test_should_deny_an_abbreviation_in_a_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "The API deploy is fixed."}
    )
    assert exit_code == 2
    assert 'Abbreviation "API"' in stderr_text


def test_should_allow_an_abbreviation_inside_a_pull_request_link(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        REPLY_TOOL_NAME,
        {"text": "It merged in [PR 5256](https://github.com/owner/repo/pull/5256)."},
    )
    assert exit_code == 0


def test_should_deny_a_tracker_item_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "Item 6 is ready for you."}
    )
    assert exit_code == 2
    assert 'Tracker number "Item 6"' in stderr_text


def test_should_deny_an_abbreviation_in_a_decision_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DECISION_TOOL_NAME,
        {"question": "Ship the API fix?", "options": [{"label": "Ship it", "consequence": "It merges."}]},
    )
    assert exit_code == 2
    assert 'Abbreviation "API"' in stderr_text


def test_should_deny_two_sentences_with_no_visual_this_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "t.jsonl",
        [prompt_entry("why did the deploy stop"), tool_call_entry("Bash")],
    )
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": TWO_SENTENCE_REPLY}, transcript_path
    )
    assert exit_code == 2
    assert "no visual this turn" in stderr_text


def test_should_allow_two_sentences_after_a_widget_this_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "t.jsonl",
        [prompt_entry("why did the deploy stop"), tool_call_entry(WIDGET_TOOL_NAME)],
    )
    exit_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": TWO_SENTENCE_REPLY}, transcript_path
    )
    assert exit_code == 0


def test_should_deny_when_the_only_widget_came_before_the_last_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "t.jsonl",
        [
            prompt_entry("why did the deploy stop"),
            tool_call_entry(WIDGET_TOOL_NAME),
            prompt_entry("and the logs"),
        ],
    )
    exit_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": TWO_SENTENCE_REPLY}, transcript_path
    )
    assert exit_code == 2


def test_should_allow_one_sentence_with_no_visual(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(tmp_path / "t.jsonl", [prompt_entry("merge it")])
    exit_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "It merged."}, transcript_path
    )
    assert exit_code == 0


def test_should_deny_an_anchor_link_inside_widget_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        WIDGET_TOOL_NAME,
        {"widget_code": '<div><a href="https://claude.ai/artifact/x">Review page</a></div>'},
    )
    assert exit_code == 2
    assert "does not open in the Claude app" in stderr_text


def test_should_allow_widget_code_with_no_anchor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch, capsys, WIDGET_TOOL_NAME, {"widget_code": "<div>Three steps</div>"}
    )
    assert exit_code == 0


def test_should_skip_the_mode_checks_when_the_switch_turns_the_mode_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    turn_mode_off(tmp_path)
    transcript_path = write_transcript(tmp_path / "t.jsonl", [prompt_entry("status")])
    all_exit_codes = [
        run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "The API deploy is fixed."})[0],
        run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "Which build ships first?"})[0],
        run_gate(
            monkeypatch, capsys, REPLY_TOOL_NAME, {"text": TWO_SENTENCE_REPLY}, transcript_path
        )[0],
        run_gate(monkeypatch, capsys, WIDGET_TOOL_NAME, {"widget_code": '<a href="x">go</a>'})[0],
    ]
    assert all_exit_codes == [0, 0, 0, 0]


def test_should_keep_the_length_check_when_the_mode_is_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    turn_mode_off(tmp_path)
    exit_code, _ = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "One. Two. Three. Four."})
    assert exit_code == 2
