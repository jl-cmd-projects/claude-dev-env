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

It denies a sentence that guesses, estimates, hedges a duration, or admits
a check did not run::

    flag: My guess is one to two hours.
    flag: I didn't confirm this one.
    ok:   The last build took 39 minutes.

It denies an Actions run, a pull request link, or a run, job, or check id
that no successful tool result in the transcript shows. A subagent's report
is the result of its Agent call. With no readable transcript, this check
is skipped.

The banned-word, unvalidated claim, and citation checks also read the prose of a
decision card: its question, its context, and each option's label and
consequence. They read an AskUserQuestion card the same way: each
question, its header, and each option's label and description.
A decision card gets a length check on its question, context, reason, and
each option's consequence. No sentence there runs longer than
MAXIMUM_WORDS_PER_SENTENCE words, and the context holds at most
MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT sentences. A context may hold no list
item line, such as "- Cedar" or "1. Cedar". A card refused for length or for
a list names the page flow to use instead: an Artifact page with a tap button
per item and a Send button, then a short reply that links the page.

Each non-empty line counts as its own sentence, so a list counts one
sentence per item. URLs, markdown link targets, inline code spans, and
fenced blocks carry no words.

With visual reply mode on, the gate also runs the checks in
``visual_reply_rules.py``. The mode is off until
``~/.claude/visual-reply-mode.json`` holds ``{"enabled": true}``. A reply
or a decision card may hold no abbreviation and no tracker number outside
a link. A reply of more than one sentence needs a widget or a page earlier
in the turn. A turn sends one reply, so a reply after a delivered reply in
the same turn is denied. A widget may hold no anchor link, since a widget
link does not open in the Claude app.

A length limit is a smell elsewhere in this package, recorded and fixed in a
later pass. A posted reply reaches the user the moment it sends and has no
later pass, so this gate denies it and the model resends a shorter one.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from json_file_reader import read_json_object
from visual_reply_rules import (
    VisualReplyRules,
    abbreviation_violation,
    load_rules,
    mode_enabled,
    second_reply_violation,
    successful_result_text,
    visual_violation,
    widget_anchor_violation,
    widget_flowchart_advice,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.reply_length_gate_constants import (
    ALL_CHECKED_TOOL_NAMES,
    ALL_DECISION_CARD_LENGTH_KEYS,
    ALL_DECISION_CARD_PROSE_KEYS,
    ALL_DECISION_OPTION_LENGTH_KEYS,
    ALL_DECISION_OPTION_PROSE_KEYS,
    ALL_DEFAULT_BANNED_WORDS,
    ALL_EVIDENCE_PATTERNS,
    ALL_QUESTION_CARD_PROSE_KEYS,
    ALL_QUESTION_OPTION_PROSE_KEYS,
    ALLOW_EXIT_CODE,
    BANNED_WORD_MESSAGE,
    BANNED_WORD_PART_SEPARATOR,
    BANNED_WORD_PATTERN_TEMPLATE,
    BANNED_WORDS_FILE_NAME,
    BANNED_WORDS_JSON_KEY,
    BANNED_WORDS_PATH_ENV_VAR,
    BLOCK_EXIT_CODE,
    CARD_CONTEXT_LIST_MESSAGE,
    CARD_CONTEXT_TOO_LONG_MESSAGE,
    CARD_FORMAT_FLOW_INSTRUCTION,
    CARD_LIST_ITEM_PATTERN,
    CAUSAL_CLAIM_PATTERN,
    CARD_TEXT_SEPARATOR,
    CITED_NUMBER_IN_RESULT_TEMPLATE,
    CITED_NUMBER_PATTERN,
    CLAUDE_HOME_DIRECTORY_NAME,
    CONFIG_FILE_ENCODING,
    CURLY_APOSTROPHE,
    DECISION_CARD_CONTEXT_KEY,
    DECISION_CARD_OPTIONS_KEY,
    DECISION_CARD_TOOL_NAME,
    DURATION_CLAIM_PATTERN,
    EM_DASH_MESSAGE,
    EM_DASH_PATTERN,
    FENCED_BLOCK_PATTERN,
    ADDITIONAL_CONTEXT_KEY,
    HOOK_EVENT_NAME,
    INLINE_CODE_PATTERN,
    LINE_BREAK_PATTERN,
    LINK_TARGET_PATTERN,
    LONG_SENTENCE_MESSAGE,
    MARKDOWN_LINK_PATTERN,
    MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT,
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
    MID_SENTENCE_COLON_MESSAGE,
    MID_SENTENCE_COLON_PATTERN,
    QUESTION_CARD_QUESTIONS_KEY,
    QUESTION_CARD_TOOL_NAME,
    RETRY_INSTRUCTION,
    SENTENCE_END_PATTERN,
    SENTENCE_PREVIEW_SUFFIX,
    SENTENCE_PREVIEW_WORD_COUNT,
    STRAIGHT_APOSTROPHE,
    TEXT_KEY,
    TOO_MANY_SENTENCES_MESSAGE,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TRANSCRIPT_PATH_KEY,
    UNLINKED_PULL_REQUEST_MESSAGE,
    UNLINKED_PULL_REQUEST_PATTERN,
    UNSEEN_CITATION_MESSAGE,
    UNSOURCED_CAUSE_MESSAGE,
    UNVALIDATED_CLAIM_MESSAGE,
    UNVALIDATED_CLAIM_PATTERN,
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
    all_word_lists = [
        WORD_PATTERN.findall(each_sentence) for each_sentence in prose_sentences(countable_text(reply_text))
    ]
    return [each_word_list for each_word_list in all_word_lists if each_word_list]


def length_violation(reply_text: str) -> str | None:
    """Return the deny reason for an over-long reply, or None when it fits."""
    all_sentences = sentence_word_lists(reply_text)
    if len(all_sentences) > MAXIMUM_SENTENCE_COUNT:
        return TOO_MANY_SENTENCES_MESSAGE.format(
            sentence_count=len(all_sentences), sentence_limit=MAXIMUM_SENTENCE_COUNT
        )
    return long_sentence_violation(reply_text)


def long_sentence_violation(prose_text: str) -> str | None:
    """Return the deny reason for the first sentence over the word limit, or None."""
    for each_sentence in sentence_word_lists(prose_text):
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


def prose_sentences(reply_text: str) -> list[str]:
    """Split the text outside fenced blocks into sentences, one per line or terminal mark."""
    return [
        each_sentence.strip()
        for each_line in LINE_BREAK_PATTERN.split(FENCED_BLOCK_PATTERN.sub(" ", reply_text))
        for each_sentence in SENTENCE_END_PATTERN.split(each_line)
    ]


def unsourced_cause_violation(reply_text: str) -> str | None:
    """Return the deny reason for the first causal sentence that cites no evidence itself, or None."""
    for each_sentence in prose_sentences(reply_text):
        is_causal = CAUSAL_CLAIM_PATTERN.search(INLINE_CODE_PATTERN.sub(" ", each_sentence))
        has_evidence = any(each_pattern.search(each_sentence) for each_pattern in ALL_EVIDENCE_PATTERNS)
        if is_causal and not has_evidence:
            return UNSOURCED_CAUSE_MESSAGE.format(sentence=each_sentence.strip())
    return None


def prose_outside_links(reply_text: str) -> str:
    """Remove fenced blocks, code spans, whole markdown links and URLs."""
    without_fences = FENCED_BLOCK_PATTERN.sub(" ", reply_text)
    without_code = INLINE_CODE_PATTERN.sub(" ", without_fences)
    without_links = MARKDOWN_LINK_PATTERN.sub(" ", without_code)
    return URL_PATTERN.sub(" ", without_links)


def unlinked_pull_request_violation(reply_text: str) -> str | None:
    """Return the deny reason for a pull request number outside a link, or None."""
    unlinked_match = UNLINKED_PULL_REQUEST_PATTERN.search(prose_outside_links(reply_text))
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


def unvalidated_claim_violation(reply_text: str) -> str | None:
    """Return the deny reason quoting the first sentence that guesses or admits a skipped check, or None.

    A duration counts as a guess unless its sentence cites the run, job, check,
    or pull request that measured it::

        flag: It should take about 40 minutes.
        ok:   The last queue build took 39 minutes, run 18239174012.
    """
    for each_sentence in prose_sentences(reply_text):
        prose_text = countable_text(each_sentence).replace(CURLY_APOSTROPHE, STRAIGHT_APOSTROPHE)
        is_guess = UNVALIDATED_CLAIM_PATTERN.search(prose_text) is not None
        is_uncited_duration = (
            DURATION_CLAIM_PATTERN.search(prose_text) is not None
            and CITED_NUMBER_PATTERN.search(each_sentence) is None
        )
        if is_guess or is_uncited_duration:
            return UNVALIDATED_CLAIM_MESSAGE.format(claim=each_sentence)
    return None


def unseen_citation_violation(reply_text: str, transcript_path: object) -> str | None:
    """Return the deny reason for the first cited run, job, check, or pull request no tool result shows.

    Returns None when the text cites nothing or the transcript cannot be read.
    """
    all_citations = list(CITED_NUMBER_PATTERN.finditer(FENCED_BLOCK_PATTERN.sub(" ", reply_text)))
    if not all_citations:
        return None
    result_text = successful_result_text(transcript_path)
    if result_text is None:
        return None
    for each_match in all_citations:
        cited_number = next(each_group for each_group in each_match.groups() if each_group)
        if re.search(CITED_NUMBER_IN_RESULT_TEMPLATE.format(number=cited_number), result_text) is None:
            return UNSEEN_CITATION_MESSAGE.format(citation=each_match.group(0))
    return None


def all_card_texts(
    all_card_input: dict[str, object],
    all_card_keys: tuple[str, ...],
    all_option_keys: tuple[str, ...],
) -> list[str]:
    """Collect the named string fields of a decision card and of each of its options."""
    all_options = all_card_input.get(DECISION_CARD_OPTIONS_KEY)
    all_option_fields = [
        each_option.get(each_key)
        for each_option in (all_options if isinstance(all_options, list) else [])
        if isinstance(each_option, dict)
        for each_key in all_option_keys
    ]
    all_card_fields = [all_card_input.get(each_key) for each_key in all_card_keys]
    return [
        each_field
        for each_field in all_card_fields + all_option_fields
        if isinstance(each_field, str)
    ]


def card_length_violation(all_card_input: dict[str, object]) -> str | None:
    """Return the deny reason, with the page flow to use, for an over-long or listed card."""
    violation = card_shape_violation(all_card_input)
    return None if violation is None else violation + CARD_FORMAT_FLOW_INSTRUCTION


def card_shape_violation(all_card_input: dict[str, object]) -> str | None:
    """Return the deny reason for a listed or over-long card context or card sentence, or None."""
    context_text = all_card_input.get(DECISION_CARD_CONTEXT_KEY)
    if isinstance(context_text, str):
        if CARD_LIST_ITEM_PATTERN.search(countable_text(context_text)) is not None:
            return CARD_CONTEXT_LIST_MESSAGE
        context_sentence_count = len(sentence_word_lists(context_text))
        if context_sentence_count > MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT:
            return CARD_CONTEXT_TOO_LONG_MESSAGE.format(
                sentence_count=context_sentence_count,
                sentence_limit=MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT,
            )
    all_length_checked_texts = all_card_texts(
        all_card_input, ALL_DECISION_CARD_LENGTH_KEYS, ALL_DECISION_OPTION_LENGTH_KEYS
    )
    for each_text in all_length_checked_texts:
        violation = long_sentence_violation(each_text)
        if violation is not None:
            return violation
    return None


def all_question_card_texts(all_card_input: dict[str, object]) -> list[str]:
    """Collect the prose fields of a question card: each question, its header, and each option's text."""
    all_questions = all_card_input.get(QUESTION_CARD_QUESTIONS_KEY)
    all_question_fields: list[object] = []
    for each_question in all_questions if isinstance(all_questions, list) else []:
        if not isinstance(each_question, dict):
            continue
        all_question_fields.extend(each_question.get(each_key) for each_key in ALL_QUESTION_CARD_PROSE_KEYS)
        all_options = each_question.get(DECISION_CARD_OPTIONS_KEY)
        all_question_fields.extend(
            each_option.get(each_key)
            for each_option in (all_options if isinstance(all_options, list) else [])
            if isinstance(each_option, dict)
            for each_key in ALL_QUESTION_OPTION_PROSE_KEYS
        )
    return [each_field for each_field in all_question_fields if isinstance(each_field, str)]


def active_mode_rules() -> VisualReplyRules | None:
    """Return the visual reply rules when the mode is on and the rule file parses."""
    if not mode_enabled(Path.home() / CLAUDE_HOME_DIRECTORY_NAME):
        return None
    return load_rules()


def card_violation(card_text: str, mode_rules: VisualReplyRules | None) -> str | None:
    """Return the deny reason for a decision card's prose, or None."""
    return (
        banned_word_violation(card_text, configured_banned_words())
        or unvalidated_claim_violation(card_text)
    ) or (
        None if mode_rules is None else abbreviation_violation(prose_outside_links(card_text), mode_rules)
    )


def reply_violation(
    reply_text: str, transcript_path: object, mode_rules: VisualReplyRules | None
) -> str | None:
    """Return the deny reason for a reply's text, or None."""
    violation = (
        length_violation(reply_text)
        or mid_sentence_colon_violation(reply_text)
        or em_dash_violation(reply_text)
        or unlinked_pull_request_violation(reply_text)
        or unsourced_cause_violation(reply_text)
        or banned_word_violation(reply_text, configured_banned_words())
        or unvalidated_claim_violation(reply_text)
        or unseen_citation_violation(reply_text, transcript_path)
    )
    if violation is not None or mode_rules is None:
        return violation
    prose_text = prose_outside_links(reply_text)
    return (
        abbreviation_violation(prose_text, mode_rules)
        or second_reply_violation(transcript_path, mode_rules)
        or visual_violation(len(sentence_word_lists(reply_text)), transcript_path, mode_rules)
    )


def tool_violation(
    tool_name: object, all_tool_input: dict[str, object], transcript_path: object = None
) -> tuple[str, str] | None:
    """Return the deny reason and the checked text for one call, or None when it passes."""
    mode_rules = active_mode_rules()
    if isinstance(tool_name, str) and mode_rules is not None:
        anchor_violation = widget_anchor_violation(tool_name, all_tool_input)
        if anchor_violation is not None:
            return anchor_violation, str(all_tool_input)
    if tool_name in (DECISION_CARD_TOOL_NAME, QUESTION_CARD_TOOL_NAME):
        if tool_name == DECISION_CARD_TOOL_NAME:
            all_texts = all_card_texts(
                all_tool_input, ALL_DECISION_CARD_PROSE_KEYS, ALL_DECISION_OPTION_PROSE_KEYS
            )
            shape_violation = card_length_violation(all_tool_input)
        else:
            all_texts = all_question_card_texts(all_tool_input)
            shape_violation = None
        card_text = CARD_TEXT_SEPARATOR.join(all_texts)
        violation = (
            shape_violation
            or card_violation(card_text, mode_rules)
            or unseen_citation_violation(card_text, transcript_path)
        )
        return None if violation is None else (violation, card_text)
    if tool_name not in ALL_CHECKED_TOOL_NAMES:
        return None
    reply_text = all_tool_input.get(TEXT_KEY)
    if not isinstance(reply_text, str):
        return None
    violation = reply_violation(reply_text, transcript_path, mode_rules)
    return None if violation is None else (violation, reply_text)


def write_flowchart_advice(tool_name: object, all_tool_input: dict[str, object]) -> None:
    """Print the flowchart advice for an allowed widget call that is not a flowchart."""
    mode_rules = active_mode_rules()
    if not isinstance(tool_name, str) or mode_rules is None:
        return
    advice = widget_flowchart_advice(tool_name, all_tool_input, mode_rules)
    if advice is None:
        return
    hook_event_output = {HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME, ADDITIONAL_CONTEXT_KEY: advice}
    sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    checked = tool_violation(tool_name, tool_input, hook_input.get(TRANSCRIPT_PATH_KEY))
    if checked is None:
        write_flowchart_advice(tool_name, tool_input)
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
