#!/usr/bin/env python3
"""PreToolUse hook that caps the length of a chat reply before it posts.

The gate reads the ``text`` field of the chat tools that post to the user.
It denies the call when the text holds more than MAXIMUM_SENTENCE_COUNT
sentences, or a sentence longer than MAXIMUM_WORDS_PER_SENTENCE words.
It also denies a pull request number the reader cannot open::

    flag: Both land in PR 5256.
    flag: It merged in #4347.
    ok:   Both land in [PR 5256](https://github.com/owner/repo/pull/5256).

It denies a colon that joins two clauses on one line, and an em dash::

    flag: That second reading matters: one message added 6.7k.
    ok:   That second reading matters. One message added 6.7k.
    ok:   Two checks failed at 9:47, then the list follows:
          (each item on its own line below the colon)

It denies a causal sentence ("so", "because", "caused", "due to",
"therefore", "means") that carries no inline code, URL, or markdown link
of its own. A command block in the same reply is no evidence::

    flag: That window was Windows PowerShell without Administrator, so the write did not land.
    ok:   The write did not land, because the next read printed `Right after write: 1`.

It denies a banned word or phrase, matched whole and case-insensitive::

    flag: The cause is likely the cache.
    ok:   The cache log shows the miss at 12:04.

The gate uses the ``banned_words`` list in ``~/.claude/reply-banned-words.json``,
or in the file that CLAUDE_REPLY_BANNED_WORDS_PATH names. Without a valid
list there, it uses ALL_DEFAULT_BANNED_WORDS.

The banned-word check also reads the prose of a decision card: its question,
its context, and each option's label and consequence.
A decision card gets no length check.

Each non-empty line counts as its own sentence, so a list counts one
sentence per item. URLs, markdown link targets, inline code spans, and
fenced blocks carry no words.

A length limit is a smell elsewhere in this package, recorded and fixed in a
later pass. A posted reply reaches the user the moment it sends and has no
later pass, so this gate denies it and the model resends a shorter one.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from json_file_reader import read_json_object
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.reply_length_gate_constants import (
    ALL_CHECKED_TOOL_NAMES,
    ALL_DECISION_CARD_PROSE_KEYS,
    ALL_DECISION_OPTION_PROSE_KEYS,
    ALL_DEFAULT_BANNED_WORDS,
    ALL_EVIDENCE_PATTERNS,
    ALLOW_EXIT_CODE,
    BANNED_WORD_MESSAGE,
    BANNED_WORD_PART_SEPARATOR,
    BANNED_WORD_PATTERN_TEMPLATE,
    BANNED_WORDS_FILE_NAME,
    BANNED_WORDS_JSON_KEY,
    BANNED_WORDS_PATH_ENV_VAR,
    BLOCK_EXIT_CODE,
    CAUSAL_CLAIM_PATTERN,
    CARD_TEXT_SEPARATOR,
    CLAUDE_HOME_DIRECTORY_NAME,
    CONFIG_FILE_ENCODING,
    DECISION_CARD_OPTIONS_KEY,
    DECISION_CARD_TOOL_NAME,
    EM_DASH_MESSAGE,
    EM_DASH_PATTERN,
    FENCED_BLOCK_PATTERN,
    HOOK_EVENT_NAME,
    INLINE_CODE_PATTERN,
    LINE_BREAK_PATTERN,
    LINK_TARGET_PATTERN,
    LONG_SENTENCE_MESSAGE,
    MARKDOWN_LINK_PATTERN,
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
    MID_SENTENCE_COLON_MESSAGE,
    MID_SENTENCE_COLON_PATTERN,
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
    UNSOURCED_CAUSE_MESSAGE,
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


def mid_sentence_colon_violation(reply_text: str) -> str | None:
    """Return the deny reason for a colon followed by prose on its line, or None."""
    if MID_SENTENCE_COLON_PATTERN.search(countable_text(reply_text)) is None:
        return None
    return MID_SENTENCE_COLON_MESSAGE


def em_dash_violation(reply_text: str) -> str | None:
    """Return the deny reason for an em dash in the prose, or None."""
    if EM_DASH_PATTERN.search(countable_text(reply_text)) is None:
        return None
    return EM_DASH_MESSAGE


def unsourced_cause_violation(reply_text: str) -> str | None:
    """Return the deny reason for the first causal sentence that cites no evidence itself, or None."""
    for each_line in LINE_BREAK_PATTERN.split(FENCED_BLOCK_PATTERN.sub(" ", reply_text)):
        for each_sentence in SENTENCE_END_PATTERN.split(each_line):
            if CAUSAL_CLAIM_PATTERN.search(INLINE_CODE_PATTERN.sub(" ", each_sentence)) is None:
                continue
            if any(each_pattern.search(each_sentence) for each_pattern in ALL_EVIDENCE_PATTERNS):
                continue
            return UNSOURCED_CAUSE_MESSAGE.format(sentence=each_sentence.strip())
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


def banned_words_config_path() -> Path:
    """Return the banned-words file named by the environment, or the one in the Claude home."""
    path_override = os.environ.get(BANNED_WORDS_PATH_ENV_VAR)
    if path_override:
        return Path(path_override)
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME / BANNED_WORDS_FILE_NAME


def configured_banned_words() -> tuple[str, ...]:
    """Return the configured banned words, or the defaults when no valid list is configured."""
    config_document = read_json_object(banned_words_config_path(), CONFIG_FILE_ENCODING)
    if config_document is None:
        return ALL_DEFAULT_BANNED_WORDS
    all_configured_words = config_document.get(BANNED_WORDS_JSON_KEY)
    if not isinstance(all_configured_words, list):
        return ALL_DEFAULT_BANNED_WORDS
    return tuple(
        each_word.strip()
        for each_word in all_configured_words
        if isinstance(each_word, str) and each_word.strip()
    )


def banned_word_violation(reply_text: str, all_banned_words: tuple[str, ...]) -> str | None:
    """Return the deny reason for the first banned word in the prose, or None."""
    prose_text = countable_text(reply_text)
    for each_banned_word in all_banned_words:
        word_pattern = BANNED_WORD_PART_SEPARATOR.join(
            re.escape(each_part) for each_part in each_banned_word.split()
        )
        whole_word_pattern = BANNED_WORD_PATTERN_TEMPLATE.format(word_pattern=word_pattern)
        if re.search(whole_word_pattern, prose_text, re.IGNORECASE):
            return BANNED_WORD_MESSAGE.format(banned_word=each_banned_word)
    return None


def all_card_texts(all_card_input: dict[str, object]) -> list[str]:
    """Collect the prose fields of a decision card: question, context, and each option's text."""
    all_options = all_card_input.get(DECISION_CARD_OPTIONS_KEY)
    all_option_fields = [
        each_option.get(each_key)
        for each_option in (all_options if isinstance(all_options, list) else [])
        if isinstance(each_option, dict)
        for each_key in ALL_DECISION_OPTION_PROSE_KEYS
    ]
    all_card_fields = [all_card_input.get(each_key) for each_key in ALL_DECISION_CARD_PROSE_KEYS]
    return [
        each_field
        for each_field in all_card_fields + all_option_fields
        if isinstance(each_field, str)
    ]


def tool_violation(tool_name: object, all_tool_input: dict[str, object]) -> tuple[str, str] | None:
    """Return the deny reason and the checked text for one call, or None when it passes."""
    if tool_name == DECISION_CARD_TOOL_NAME:
        card_text = CARD_TEXT_SEPARATOR.join(all_card_texts(all_tool_input))
        card_violation = banned_word_violation(card_text, configured_banned_words())
        return None if card_violation is None else (card_violation, card_text)
    if tool_name not in ALL_CHECKED_TOOL_NAMES:
        return None
    reply_text = all_tool_input.get(TEXT_KEY)
    if not isinstance(reply_text, str):
        return None
    violation = (
        length_violation(reply_text)
        or mid_sentence_colon_violation(reply_text)
        or em_dash_violation(reply_text)
        or unlinked_pull_request_violation(reply_text)
        or unsourced_cause_violation(reply_text)
        or banned_word_violation(reply_text, configured_banned_words())
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
