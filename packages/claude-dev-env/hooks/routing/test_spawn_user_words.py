import json
from pathlib import Path

import spawn_user_words
from hooks_constants.spawn_oversight_hook_constants import (
    MISMATCHED_USER_WORDS_REASON,
    MISSING_USER_WORDS_REASON,
)

SESSION_WORDS = "Send me X's output in this thread."
BRIEF_WITH_WORDS = (
    f"User's words:\n```\n{SESSION_WORDS}\n```\nOutcome: the output is in the thread."
)


def _write_transcript(tmp_path: Path, all_entries: list[dict[str, object]]) -> str:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries), encoding="utf-8"
    )
    return str(transcript_path)


def _user_entry(content: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": content}}


def _assistant_entry(text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def test_quoted_user_words_should_return_the_fenced_block_after_the_marker() -> None:
    assert spawn_user_words.quoted_user_words(BRIEF_WITH_WORDS) == f"{SESSION_WORDS}\n"


def test_quoted_user_words_should_accept_a_bold_marker() -> None:
    brief = f"**User's words:**\n```\n{SESSION_WORDS}\n```\n"
    assert spawn_user_words.quoted_user_words(brief) == f"{SESSION_WORDS}\n"


def test_quoted_user_words_should_return_none_without_a_block() -> None:
    assert spawn_user_words.quoted_user_words("Outcome: the output is in the thread.") is None


def test_session_user_text_should_join_user_text_in_order_and_unescape_it(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path, [_user_entry("Send me X&#39;s output."), _user_entry("Thanks.")]
    )
    assert spawn_user_words.session_user_text(transcript_path) == "Send me X's output. Thanks."


def test_session_user_text_should_leave_out_assistant_entries(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path, [_user_entry("Fix the parser."), _assistant_entry("Send me X's output.")]
    )
    assert spawn_user_words.session_user_text(transcript_path) == "Fix the parser."


def test_session_user_text_should_leave_out_meta_entries(tmp_path: Path) -> None:
    meta_entry = {**_user_entry("Injected context."), "isMeta": True}
    transcript_path = _write_transcript(tmp_path, [meta_entry, _user_entry("Fix the parser.")])
    assert spawn_user_words.session_user_text(transcript_path) == "Fix the parser."


def test_session_user_text_should_return_empty_for_an_unreadable_transcript(tmp_path: Path) -> None:
    assert spawn_user_words.session_user_text(str(tmp_path / "missing.jsonl")) == ""
    assert spawn_user_words.session_user_text(None) == ""


def test_user_words_gaps_should_name_a_missing_block() -> None:
    assert spawn_user_words.user_words_gaps("Outcome: done.", None) == [MISSING_USER_WORDS_REASON]


def test_user_words_gaps_should_name_a_paraphrase(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_user_entry(SESSION_WORDS)])
    paraphrase = BRIEF_WITH_WORDS.replace(SESSION_WORDS, "Give me the X output.")
    assert spawn_user_words.user_words_gaps(paraphrase, transcript_path) == [
        MISMATCHED_USER_WORDS_REASON
    ]


def test_user_words_gaps_should_pass_a_word_for_word_quote(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_user_entry(SESSION_WORDS)])
    assert spawn_user_words.user_words_gaps(BRIEF_WITH_WORDS, transcript_path) == []


def test_user_words_gaps_should_pass_when_there_is_no_transcript_to_compare(tmp_path: Path) -> None:
    assert spawn_user_words.user_words_gaps(BRIEF_WITH_WORDS, str(tmp_path / "missing.jsonl")) == []
