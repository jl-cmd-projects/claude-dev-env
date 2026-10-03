#!/usr/bin/env python3
"""PreToolUse hook that caps the length of a chat reply before it posts.

The gate reads the ``text`` field of the chat tools that post to the user.
It denies the call when the text holds more than MAXIMUM_SENTENCE_COUNT
sentences, or a sentence longer than MAXIMUM_WORDS_PER_SENTENCE words.
It also denies a pull request number the reader cannot open, and a hedge
word that marks a claim nobody checked::

    flag: Both land in PR 5256.
    flag: It merged in #4347.
    ok:   Both land in [PR 5256](https://github.com/owner/repo/pull/5256).
    flag: The call button likely gets flagged in 7.
    ok:   The call button is flagged in 7, per the crops.

The hedge check also reads every text field of a decision card.

Each non-empty line counts as its own sentence, so a list counts one
sentence per item. URLs, markdown link targets, inline code spans, and
fenced blocks carry no words.

A length limit is a smell elsewhere in this package, recorded and fixed in a
later pass. A posted reply reaches the user the moment it sends and has no
later pass, so this gate denies it and the model resends a shorter one.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.verify_before_acting_constants import HEDGE_PATTERN
from hooks_constants.reply_length_gate_constants import (
    ALL_CHECKED_TOOL_NAMES,
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    CARD_TEXT_SEPARATOR,
    DECISION_CARD_TOOL_NAME,
    FENCED_BLOCK_PATTERN,
    HEDGE_MESSAGE,
    HOOK_EVENT_NAME,
    INLINE_CODE_PATTERN,
    LINE_BREAK_PATTERN,
    LINK_TARGET_PATTERN,
    LONG_SENTENCE_MESSAGE,
    MARKDOWN_LINK_PATTERN,
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
    RETRY_INSTRUCTION,
    SENTENCE_END_PATTERN,
    SENTENCE_PREVIEW_SUFFIX,
    SENTENCE_PREVIEW_WORD_COUNT,
    TEXT_KEY,
    TOO_MANY_SENTENCES_MESSAGE,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    UNLINKED_PULL_REQUEST_MESSAGE,
    UNLINKED_PULL_REQUEST_PATTERN,
    URL_PATTERN,
    WORD_PATTERN,
    WORD_SEPARATOR,
)


def countable_text(reply_text: str) -> str:
    """Remove the spans that carry no words: fenced blocks, code, link targets, URLs."""
    without_fences = FENCED_BLOCK_PATTERN.sub(" ", reply_text)
    without_code = INLINE_CODE_PATTERN.sub(" ", without_fences)
    without_link_targets = LINK_TARGET_PATTERN.sub("]", without_code)
    return URL_PATTERN.sub(" ", without_link_targets)


def sentence_word_lists(reply_text: str) -> list[list[str]]:
    """Split the text into sentences, one per line or terminal mark, as word lists."""
    all_sentence_texts = [
        each_sentence
        for each_line in LINE_BREAK_PATTERN.split(countable_text(reply_text))
        for each_sentence in SENTENCE_END_PATTERN.split(each_line)
    ]
    all_word_lists = [WORD_PATTERN.findall(each_sentence) for each_sentence in all_sentence_texts]
    return [each_word_list for each_word_list in all_word_lists if each_word_list]


def length_violation(reply_text: str) -> str | None:
    """Return the deny reason for an over-long reply, or None when it fits."""
    all_sentences = sentence_word_lists(reply_text)
    if len(all_sentences) > MAXIMUM_SENTENCE_COUNT:
        return TOO_MANY_SENTENCES_MESSAGE.format(
            sentence_count=len(all_sentences), sentence_limit=MAXIMUM_SENTENCE_COUNT
        )
    for each_sentence in all_sentences:
        if len(each_sentence) > MAXIMUM_WORDS_PER_SENTENCE:
            sentence_preview = WORD_SEPARATOR.join(each_sentence[:SENTENCE_PREVIEW_WORD_COUNT])
            return LONG_SENTENCE_MESSAGE.format(
                word_count=len(each_sentence),
                word_limit=MAXIMUM_WORDS_PER_SENTENCE,
                sentence_preview=sentence_preview + SENTENCE_PREVIEW_SUFFIX,
            )
    return None


def unlinked_pull_request_violation(reply_text: str) -> str | None:
    """Return the deny reason for a pull request number outside a link, or None."""
    without_fences = FENCED_BLOCK_PATTERN.sub(" ", reply_text)
    without_code = INLINE_CODE_PATTERN.sub(" ", without_fences)
    without_links = MARKDOWN_LINK_PATTERN.sub(" ", without_code)
    unlinked_match = UNLINKED_PULL_REQUEST_PATTERN.search(URL_PATTERN.sub(" ", without_links))
    if unlinked_match is None:
        return None
    return UNLINKED_PULL_REQUEST_MESSAGE.format(reference=unlinked_match.group(0))


def hedge_violation(reply_text: str) -> str | None:
    """Return the deny reason for the first hedged sentence, or None when none hedges."""
    all_sentences = [
        each_sentence
        for each_line in LINE_BREAK_PATTERN.split(countable_text(reply_text))
        for each_sentence in SENTENCE_END_PATTERN.split(each_line)
    ]
    for each_sentence in all_sentences:
        hedge_match = HEDGE_PATTERN.search(each_sentence)
        if hedge_match is None:
            continue
        all_words = WORD_PATTERN.findall(each_sentence)
        return HEDGE_MESSAGE.format(
            hedge=hedge_match.group(0),
            sentence_preview=WORD_SEPARATOR.join(all_words[:SENTENCE_PREVIEW_WORD_COUNT])
            + SENTENCE_PREVIEW_SUFFIX,
        )
    return None


def all_card_texts(card_value: object) -> list[str]:
    """Collect every string inside a decision card's input, in order."""
    if isinstance(card_value, str):
        return [card_value]
    if isinstance(card_value, dict):
        return [
            each_text
            for each_value in card_value.values()
            for each_text in all_card_texts(each_value)
        ]
    if isinstance(card_value, list):
        return [each_text for each_value in card_value for each_text in all_card_texts(each_value)]
    return []


def tool_violation(tool_name: object, all_tool_input: dict[str, object]) -> tuple[str, str] | None:
    """Return the deny reason and the checked text for one call, or None when it passes."""
    if tool_name == DECISION_CARD_TOOL_NAME:
        card_text = CARD_TEXT_SEPARATOR.join(all_card_texts(all_tool_input))
        card_violation = hedge_violation(card_text)
        return None if card_violation is None else (card_violation, card_text)
    if tool_name not in ALL_CHECKED_TOOL_NAMES:
        return None
    reply_text = all_tool_input.get(TEXT_KEY)
    if not isinstance(reply_text, str):
        return None
    violation = (
        length_violation(reply_text)
        or unlinked_pull_request_violation(reply_text)
        or hedge_violation(reply_text)
    )
    return None if violation is None else (violation, reply_text)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    checked = tool_violation(tool_name, tool_input)
    if checked is None:
        return ALLOW_EXIT_CODE
    violation, reply_text = checked
    block_reason = violation + RETRY_INSTRUCTION
    log_hook_block(
        Path(__file__).name,
        HOOK_EVENT_NAME,
        block_reason,
        tool_name=str(tool_name),
        offending_input_preview=reply_text,
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
