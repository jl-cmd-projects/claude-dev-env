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
    switch_path = tmp_path / ".claude" / "visual-reply-mode.json"
    switch_path.parent.mkdir(exist_ok=True)
    switch_path.write_text('{"enabled": true}', encoding="utf-8")


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
    config_path.parent.mkdir(exist_ok=True)
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
    config_path.parent.mkdir(exist_ok=True)
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
    config_path.parent.mkdir(exist_ok=True)
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


def test_should_allow_widget_code_with_no_anchor_and_advise_a_flowchart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": WIDGET_TOOL_NAME,
        "tool_input": {"widget_code": "<div>Three steps</div>"},
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = reply_length_gate.main()
    assert exit_code == 0
    advice_output = json.loads(capsys.readouterr().out)
    assert "Redraw this widget as one SVG flowchart" in advice_output["hookSpecificOutput"]["additionalContext"]


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


def test_should_deny_the_quoted_cause_with_no_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        POST_TOOL_NAME,
        {"text": "That window was Windows PowerShell without Administrator, so the write did not land."},
    )
    assert exit_code == 2
    assert "Cause with no source" in stderr_text


@pytest.mark.parametrize(
    "reply_text",
    [
        "The write did not land, because the next read printed `Right after write: 1`.",
        "The job failed because of [run 12](https://github.com/owner/repo/actions/runs/12).",
    ],
)
def test_should_allow_a_cause_that_cites_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text})
    assert (exit_code, stderr_text) == (0, "")


@pytest.mark.parametrize(
    "reply_text",
    [
        "That window lacked Administrator, so the write did not land.\n\n```powershell\nRestart-Service x\n```",
        "The error shows the hook is the only line. So the filter wrote nothing.",
        "One line survived because its start did not match my filter. Run this.",
    ],
)
def test_should_deny_a_cause_whose_own_sentence_cites_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text})
    assert exit_code == 2
    assert "Cause with no source" in stderr_text


def test_should_allow_a_reply_with_no_causal_claim(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": "The runner restarted. Also, so far so good."}
    )
    assert exit_code == 0


UPDATE_TOOL_NAME = "mcp__hearthbot__update_message"
QUESTION_CARD_TOOL_NAME = "AskUserQuestion"
RUN_LINK_REPLY = (
    "The last build passed in [run 18239174012]"
    "(https://github.com/owner/repo/actions/runs/18239174012)."
)


def write_tool_result_transcript(transcript_path: Path, result_text: str, is_error: bool = False) -> Path:
    all_entries = [
        {"type": "user", "message": {"content": "how close are we"}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]},
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": is_error,
                        "content": [{"type": "text", "text": result_text}],
                    }
                ]
            },
        },
    ]
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries), encoding="utf-8"
    )
    return transcript_path


@pytest.mark.parametrize("tool_name", [REPLY_TOOL_NAME, POST_TOOL_NAME, UPDATE_TOOL_NAME])
def test_should_deny_an_estimate_and_quote_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool_name: str
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, tool_name, {"text": "My estimate is one to two hours."}
    )
    assert exit_code == 2
    assert 'No tool validated this: "My estimate is one to two hours."' in stderr_text


@pytest.mark.parametrize(
    "reply_text",
    [
        "I didn\u2019t confirm this one.",
        "I have not checked the queue.",
        "I assumed the build passed.",
        "Run 18239174012 is unverified.",
        "About 20 minutes left.",
        "It will take two hours.",
        "ETA is 3-4 hours.",
        "Estimate from the last check is two builds.",
        "I did not run the suite.",
        "The tests have not yet been run.",
        "The job takes 39 minutes.",
        "The migration takes seventy minutes.",
        "I was not able to verify the fix.",
        "The fix has not been validated.",
        "The fix was not verified in production.",
        "The suite takes about 90 seconds.",
    ],
)
def test_should_deny_each_unvalidated_claim_shape(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text})
    assert exit_code == 2
    assert "No tool validated this" in stderr_text


@pytest.mark.parametrize(
    "reply_text",
    [
        "Two builds are left in the queue.",
        "I will check the queue again within 15 minutes.",
        "The last queue build took 39 minutes.",
        "The gate now refuses `guess` and `assumed`.",
        "The job takes 39 minutes, see run 18239174012.",
        "The hook cannot run on Windows.",
        "The crash is not a test problem.",
        "That is not the check that failed.",
        "The migration did not run out of memory.",
        "We did not run into any errors.",
        "This is not something to check before the release.",
        "The result is not what we tested for.",
        "The migration did not run on the replica.",
        "The old parser did not validate the header length.",
        "The job has not run yet.",
        "The config file is not checked in.",
        "The release branch is not checked out.",
    ],
)
def test_should_allow_a_reply_with_no_unvalidated_claim(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    assert run_gate(monkeypatch, capsys, REPLY_TOOL_NAME, {"text": reply_text}) == (0, "")


def test_should_deny_a_run_no_tool_result_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_tool_result_transcript(tmp_path / "s.jsonl", "run 18239170000 ok")
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": RUN_LINK_REPLY}, transcript_path
    )
    assert exit_code == 2
    assert 'cites "run 18239174012"' in stderr_text


def test_should_deny_a_run_only_an_error_result_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_tool_result_transcript(
        tmp_path / "s.jsonl", "run 18239174012 ok", is_error=True
    )
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": RUN_LINK_REPLY}, transcript_path
    )
    assert exit_code == 2
    assert "no tool result in this session shows it" in stderr_text


def test_should_allow_a_run_a_tool_result_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_tool_result_transcript(tmp_path / "s.jsonl", "run 18239174012 took 39m")
    assert run_gate(
        monkeypatch, capsys, REPLY_TOOL_NAME, {"text": RUN_LINK_REPLY}, transcript_path
    ) == (0, "")


def test_should_deny_a_question_card_that_admits_a_skipped_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    card = {
        "questions": [
            {
                "question": "Ship the gate now?",
                "header": "Ship",
                "options": [
                    {"label": "Ship", "description": "I did not test the Stop hook."},
                    {"label": "Wait", "description": "Run the suite first."},
                ],
            }
        ]
    }
    exit_code, stderr_text = run_gate(monkeypatch, capsys, QUESTION_CARD_TOOL_NAME, card)
    assert exit_code == 2
    assert "I did not test the Stop hook." in stderr_text


def test_should_allow_a_question_card_with_no_unvalidated_claim(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    card = {
        "questions": [
            {
                "question": "Which gate design?",
                "header": "Design",
                "options": [{"label": "Fold in", "description": "One gate checks every reply."}],
            }
        ]
    }
    assert run_gate(monkeypatch, capsys, QUESTION_CARD_TOOL_NAME, card) == (0, "")


def test_should_collect_each_question_card_prose_field() -> None:
    card = {
        "questions": [
            {"question": "Q?", "header": "H", "options": [{"label": "L", "description": "D"}, "x"]},
            "not a question",
        ]
    }
    assert reply_length_gate.all_question_card_texts(card) == ["Q?", "H", "L", "D"]


def test_should_quote_the_hedged_sentence() -> None:
    assert reply_length_gate.unvalidated_claim_violation("Done. It should take a few minutes.") == (
        'No tool validated this: "It should take a few minutes.". Run the check yourself or through'
        " a subagent, then state what the run, log line, output, or file and line shows, or leave"
        " the claim out."
    )


def test_should_skip_the_citation_check_without_a_transcript() -> None:
    assert reply_length_gate.unseen_citation_violation(RUN_LINK_REPLY, None) is None


def test_should_leave_the_transcript_unread_when_the_text_cites_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    all_read_paths: list[object] = []
    monkeypatch.setattr(reply_length_gate, "successful_result_text", all_read_paths.append)
    transcript_path = write_tool_result_transcript(tmp_path / "s.jsonl", "nothing cited")
    assert reply_length_gate.unseen_citation_violation("Two builds left.", transcript_path) is None
    assert all_read_paths == []


def test_should_split_prose_sentences_outside_fenced_blocks() -> None:
    reply_text = "First one. Second one?\n```\nskipped. code\n```\nThird"
    assert reply_length_gate.prose_sentences(reply_text) == ["First one.", "Second one?", "", "Third"]
