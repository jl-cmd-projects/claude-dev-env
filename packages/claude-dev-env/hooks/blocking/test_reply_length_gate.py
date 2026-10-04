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
) -> tuple[int, str]:
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
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
        {"text": "The fix is in. Tests pass on CI. It ships with the next release."},
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
