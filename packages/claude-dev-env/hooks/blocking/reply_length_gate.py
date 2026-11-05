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

A reply that reports results, a markdown table or three or more figures outside
links and code, needs one picture: an image file in ``attached_outputs``, or a
markdown image. This check runs whether or not the visual mode is on.

A length limit is a smell elsewhere in this package, recorded and fixed in a
later pass. A posted reply reaches the user the moment it sends and has no
later pass, so this gate denies it and the model resends a shorter one.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shlex
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from gh_post_body_texts import extract_mcp_body_texts
from json_file_reader import read_json_object
from visual_reply_rules import (
    VisualReplyRules,
    abbreviation_violation,
    load_rules,
    mode_enabled,
    results_picture_violation,
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
    ALL_CHECKED_MCP_TOOL_NAMES,
    BASH_TOOL_NAME,
    COMMAND_KEY,
    COMMENT_RETRY_INSTRUCTION,
    DETAILS_BLOCK_PATTERN,
    ALL_GH_BODY_FLAGS,
    ALL_GH_COMMENT_ACTIONS,
    ALL_GH_COMMENT_GROUPS,
    GH_BODY_FLAG_PREFIX,
    GH_PROGRAM_NAME,
    SHELL_OPERATOR_CHARACTERS,
    ALL_CHECKED_TOOL_NAMES,
    ALL_DECISION_CARD_LENGTH_KEYS,
    ALL_DECISION_CARD_PROSE_KEYS,
    ALL_DECISION_OPTION_LENGTH_KEYS,
    ALL_DECISION_OPTION_PROSE_KEYS,
    ALL_DEFAULT_BANNED_WORDS,
    ALL_EDIT_TOOL_NAMES,
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
    FINDING_SEPARATOR,
    FIX_EVERY_ITEM_INSTRUCTION,
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


def joined_violations(all_violations: Iterable[str | None]) -> str | None:
    """Join every violation found into one deny reason, one violation per line.

    ::

        []                         -> None
        ["Too long."]              -> "Too long."
        ["Too long.", "Em dash."]  -> "Too long." and "Em dash." on two lines

    None entries are skipped. A joined reason can join again at an outer
    level and stays one violation per line, so ``numbered_violations``
    numbers the whole reason once.
    """
    all_found = [each_violation for each_violation in all_violations if each_violation]
    return FINDING_SEPARATOR.join(all_found) if all_found else None


def numbered_violations(violation: str) -> str:
    """Number each line of a joined deny reason that holds several violations.

    ::

        "Too long."             -> "Too long."
        "Too long.\nEm dash."   -> "1. Too long." and "2. Em dash." on two lines
    """
    all_lines = violation.split(FINDING_SEPARATOR)
    if len(all_lines) == 1:
        return violation
    return FINDING_SEPARATOR.join(
        f"{each_position}. {each_line}" for each_position, each_line in enumerate(all_lines, start=1)
    )


def collected_violations(all_checks: Iterable[Callable[[], str | None]]) -> str | None:
    """Run every check in order and join each violation it reports.

    A check that raises ends the run. With nothing found yet the error
    propagates, which lets the call through as an early-return gate did.
    After a finding, the findings so far stand, as the first one did when
    the gate never ran the later checks.
    """
    all_violations: list[str | None] = []
    for each_check in all_checks:
        is_stopped, violation = _checked_violation(each_check, any(all_violations))
        if is_stopped:
            break
        all_violations.append(violation)
    return joined_violations(all_violations)


def _checked_violation(check: Callable[[], str | None], has_finding: bool) -> tuple[bool, str | None]:
    try:
        return False, check()
    except Exception:
        if has_finding:
            return True, None
        raise


def length_violation(reply_text: str) -> str | None:
    """Return the deny reason for an over-long reply and each over-long sentence, or None when it fits."""
    all_sentences = sentence_word_lists(reply_text)
    return joined_violations(
        [
            TOO_MANY_SENTENCES_MESSAGE.format(
                sentence_count=len(all_sentences), sentence_limit=MAXIMUM_SENTENCE_COUNT
            )
            if len(all_sentences) > MAXIMUM_SENTENCE_COUNT
            else None,
            long_sentence_violation(reply_text),
        ]
    )


def long_sentence_violation(prose_text: str) -> str | None:
    """Return the deny reason for each sentence over the word limit, or None."""
    return joined_violations(
        LONG_SENTENCE_MESSAGE.format(
            word_count=len(each_sentence),
            word_limit=MAXIMUM_WORDS_PER_SENTENCE,
            sentence_preview=WORD_SEPARATOR.join(each_sentence[:SENTENCE_PREVIEW_WORD_COUNT])
            + SENTENCE_PREVIEW_SUFFIX,
        )
        for each_sentence in sentence_word_lists(prose_text)
        if len(each_sentence) > MAXIMUM_WORDS_PER_SENTENCE
    )


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
    """Return the deny reason for each causal sentence that cites no evidence itself, or None."""
    return joined_violations(
        UNSOURCED_CAUSE_MESSAGE.format(sentence=each_sentence.strip())
        for each_sentence in prose_sentences(reply_text)
        if CAUSAL_CLAIM_PATTERN.search(INLINE_CODE_PATTERN.sub(" ", each_sentence))
        and not any(each_pattern.search(each_sentence) for each_pattern in ALL_EVIDENCE_PATTERNS)
    )


def prose_outside_links(reply_text: str) -> str:
    """Remove fenced blocks, code spans, whole markdown links and URLs."""
    without_fences = FENCED_BLOCK_PATTERN.sub(" ", reply_text)
    without_code = INLINE_CODE_PATTERN.sub(" ", without_fences)
    without_links = MARKDOWN_LINK_PATTERN.sub(" ", without_code)
    return URL_PATTERN.sub(" ", without_links)


def unlinked_pull_request_violation(reply_text: str) -> str | None:
    """Return the deny reason for each pull request number outside a link, or None."""
    return joined_violations(
        UNLINKED_PULL_REQUEST_MESSAGE.format(reference=each_match.group(0))
        for each_match in UNLINKED_PULL_REQUEST_PATTERN.finditer(prose_outside_links(reply_text))
    )


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
    """Return the deny reason for each banned word in the prose, or None."""
    prose_text = countable_text(reply_text)
    return joined_violations(
        BANNED_WORD_MESSAGE.format(banned_word=each_banned_word)
        for each_banned_word in all_banned_words
        if re.search(
            BANNED_WORD_PATTERN_TEMPLATE.format(
                word_pattern=BANNED_WORD_PART_SEPARATOR.join(
                    re.escape(each_part) for each_part in each_banned_word.split()
                )
            ),
            prose_text,
            re.IGNORECASE,
        )
    )


def unvalidated_claim_violation(reply_text: str) -> str | None:
    """Return the deny reason quoting each sentence that guesses or admits a skipped check, or None.

    A duration counts as a guess unless its sentence cites the run, job, check,
    or pull request that measured it::

        flag: It should take about 40 minutes.
        ok:   The last queue build took 39 minutes, run 18239174012.
    """
    all_claims: list[str] = []
    for each_sentence in prose_sentences(reply_text):
        prose_text = countable_text(each_sentence).replace(CURLY_APOSTROPHE, STRAIGHT_APOSTROPHE)
        is_guess = UNVALIDATED_CLAIM_PATTERN.search(prose_text) is not None
        is_uncited_duration = (
            DURATION_CLAIM_PATTERN.search(prose_text) is not None
            and CITED_NUMBER_PATTERN.search(each_sentence) is None
        )
        if is_guess or is_uncited_duration:
            all_claims.append(UNVALIDATED_CLAIM_MESSAGE.format(claim=each_sentence))
    return joined_violations(all_claims)


def unseen_citation_violation(reply_text: str, transcript_path: object) -> str | None:
    """Return the deny reason for each cited run, job, check, or pull request no tool result shows.

    Returns None when the text cites nothing or the transcript cannot be read.
    """
    all_citations = list(CITED_NUMBER_PATTERN.finditer(FENCED_BLOCK_PATTERN.sub(" ", reply_text)))
    if not all_citations:
        return None
    result_text = successful_result_text(transcript_path)
    if result_text is None:
        return None
    return joined_violations(
        UNSEEN_CITATION_MESSAGE.format(citation=each_match.group(0))
        for each_match in all_citations
        if re.search(
            CITED_NUMBER_IN_RESULT_TEMPLATE.format(
                number=next(each_group for each_group in each_match.groups() if each_group)
            ),
            result_text,
        )
        is None
    )


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
    """Return the deny reason for each listed or over-long card context and card sentence, or None."""
    context_text = all_card_input.get(DECISION_CARD_CONTEXT_KEY)
    all_violations: list[str | None] = []
    if isinstance(context_text, str):
        if CARD_LIST_ITEM_PATTERN.search(FENCED_BLOCK_PATTERN.sub(" ", context_text)) is not None:
            all_violations.append(CARD_CONTEXT_LIST_MESSAGE)
        context_sentence_count = len(sentence_word_lists(context_text))
        if context_sentence_count > MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT:
            all_violations.append(
                CARD_CONTEXT_TOO_LONG_MESSAGE.format(
                    sentence_count=context_sentence_count,
                    sentence_limit=MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT,
                )
            )
    all_length_checked_texts = all_card_texts(
        all_card_input, ALL_DECISION_CARD_LENGTH_KEYS, ALL_DECISION_OPTION_LENGTH_KEYS
    )
    all_violations.extend(long_sentence_violation(each_text) for each_text in all_length_checked_texts)
    return joined_violations(all_violations)


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
    """Return the deny reason for each problem in a decision card's prose, or None."""
    return collected_violations(
        [
            lambda: banned_word_violation(card_text, configured_banned_words()),
            lambda: unvalidated_claim_violation(card_text),
            lambda: None
            if mode_rules is None
            else abbreviation_violation(prose_outside_links(card_text), mode_rules),
        ]
    )


def reply_violation(
    reply_text: str, transcript_path: object, mode_rules: VisualReplyRules | None
) -> str | None:
    """Return the deny reason for each problem in a reply's text, or None."""
    all_checks: list[Callable[[], str | None]] = [
        lambda: length_violation(reply_text),
        lambda: mid_sentence_colon_violation(reply_text),
        lambda: em_dash_violation(reply_text),
        lambda: unlinked_pull_request_violation(reply_text),
        lambda: unsourced_cause_violation(reply_text),
        lambda: banned_word_violation(reply_text, configured_banned_words()),
        lambda: unvalidated_claim_violation(reply_text),
        lambda: unseen_citation_violation(reply_text, transcript_path),
    ]
    if mode_rules is not None:
        all_checks.extend(
            [
                lambda: abbreviation_violation(prose_outside_links(reply_text), mode_rules),
                lambda: second_reply_violation(transcript_path, mode_rules),
                lambda: visual_violation(len(sentence_word_lists(reply_text)), transcript_path, mode_rules),
            ]
        )
    return collected_violations(all_checks)


def tool_violation(
    tool_name: object, all_tool_input: dict[str, object], transcript_path: object = None
) -> tuple[str, str] | None:
    """Return the deny reason and the checked text for one call, or None when it passes."""
    mode_rules = active_mode_rules()
    anchor_violation = (
        widget_anchor_violation(tool_name, all_tool_input)
        if isinstance(tool_name, str) and mode_rules is not None
        else None
    )
    if anchor_violation is None:
        return _text_violation(tool_name, all_tool_input, transcript_path, mode_rules)
    try:
        checked = _text_violation(tool_name, all_tool_input, transcript_path, mode_rules)
    except Exception:
        checked = None
    if checked is None:
        return anchor_violation, str(all_tool_input)
    return FINDING_SEPARATOR.join([anchor_violation, checked[0]]), checked[1]


def _text_violation(
    tool_name: object,
    all_tool_input: dict[str, object],
    transcript_path: object,
    mode_rules: VisualReplyRules | None,
) -> tuple[str, str] | None:
    if tool_name in (DECISION_CARD_TOOL_NAME, QUESTION_CARD_TOOL_NAME):
        return _card_text_violation(tool_name, all_tool_input, transcript_path, mode_rules)
    if tool_name not in ALL_CHECKED_TOOL_NAMES:
        return None
    reply_text = all_tool_input.get(TEXT_KEY)
    if not isinstance(reply_text, str):
        return None
    all_checks = [lambda: reply_violation(reply_text, transcript_path, mode_rules)]
    if tool_name not in ALL_EDIT_TOOL_NAMES:
        all_checks.append(
            lambda: results_picture_violation(
                prose_outside_links(reply_text),
                reply_text,
                all_tool_input,
                mode_rules if mode_rules is not None else load_rules(),
            )
        )
    violation = collected_violations(all_checks)
    return None if violation is None else (violation, reply_text)


def _card_text_violation(
    tool_name: object,
    all_tool_input: dict[str, object],
    transcript_path: object,
    mode_rules: VisualReplyRules | None,
) -> tuple[str, str] | None:
    if tool_name == DECISION_CARD_TOOL_NAME:
        all_texts = all_card_texts(all_tool_input, ALL_DECISION_CARD_PROSE_KEYS, ALL_DECISION_OPTION_PROSE_KEYS)
        shape_violation = card_length_violation(all_tool_input)
    else:
        all_texts = all_question_card_texts(all_tool_input)
        shape_violation = None
    card_text = CARD_TEXT_SEPARATOR.join(all_texts)
    violation = collected_violations(
        [
            lambda: shape_violation,
            lambda: card_violation(card_text, mode_rules),
            lambda: unseen_citation_violation(card_text, transcript_path),
        ]
    )
    return None if violation is None else (violation, card_text)


def github_comment_texts(tool_name: object, all_tool_input: dict[str, object]) -> list[str]:
    """Return the GitHub comment texts one call would post, or an empty list.

    ::

        mcp__github__add_issue_comment {"body": "Done."}  -> ["Done."]
        Bash 'gh pr comment 12 --body "Done."'            -> ["Done."]
        Bash 'git push && gh pr comment 12 --body "Done."' -> ["Done."]
        Bash 'gh pr create --body "Long body"'            -> []
    """
    if tool_name in ALL_CHECKED_MCP_TOOL_NAMES:
        return extract_mcp_body_texts(all_tool_input)
    command = all_tool_input.get(COMMAND_KEY)
    if tool_name != BASH_TOOL_NAME or not isinstance(command, str):
        return []
    try:
        command_lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        command_lexer.whitespace_split = True
        all_command_tokens = list(command_lexer)
    except ValueError:
        return []
    return gh_comment_bodies(all_command_tokens)


def gh_comment_bodies(all_command_tokens: list[str]) -> list[str]:
    """Return the ``--body`` values of each ``gh pr|issue comment|review`` call in the tokens.

    ::

        git push && gh -R o/r pr comment 12 --body "Done."  -> ["Done."]
        gh pr create --body "Long body"                     -> []
    """
    all_bodies: list[str] = []
    for each_command_tokens in gh_command_token_runs(all_command_tokens):
        all_pairs = list(itertools.pairwise(each_command_tokens))
        if not any(
            each_group in ALL_GH_COMMENT_GROUPS and each_action in ALL_GH_COMMENT_ACTIONS
            for each_group, each_action in all_pairs
        ):
            continue
        all_bodies.extend(
            each_token[len(GH_BODY_FLAG_PREFIX):]
            for each_token in each_command_tokens
            if each_token.startswith(GH_BODY_FLAG_PREFIX)
        )
        all_bodies.extend(each_value for each_flag, each_value in all_pairs if each_flag in ALL_GH_BODY_FLAGS)
    return all_bodies


def is_command_token(token: str) -> bool:
    """Return True when the token is part of a command, False for ``&&``, ``||``, ``;`` or ``|``."""
    return not set(token) <= SHELL_OPERATOR_CHARACTERS


def gh_command_token_runs(all_command_tokens: list[str]) -> list[list[str]]:
    """Return the tokens after each ``gh`` token, up to the next shell operator."""
    all_runs: list[list[str]] = []
    for each_index, each_token in enumerate(all_command_tokens):
        if each_token == GH_PROGRAM_NAME:
            all_runs.append(list(itertools.takewhile(is_command_token, all_command_tokens[each_index + 1:])))
    return all_runs


def comment_length_violation(comment_text: str) -> str | None:
    """Return the deny reason for one over-long GitHub comment text, or None when it fits.

    Fenced code blocks and collapsed ``<details>`` blocks carry no words.
    """
    violation = length_violation(DETAILS_BLOCK_PATTERN.sub(" ", comment_text))
    return None if violation is None else violation + COMMENT_RETRY_INSTRUCTION


def github_comment_violation(tool_name: object, all_tool_input: dict[str, object]) -> tuple[str, str] | None:
    """Return the deny reason and text for every over-long GitHub comment, or None.

    Fenced code blocks and collapsed ``<details>`` blocks carry no words.
    """
    all_over_long = [
        (violation, each_comment_text)
        for each_comment_text in github_comment_texts(tool_name, all_tool_input)
        if (violation := comment_length_violation(each_comment_text)) is not None
    ]
    if not all_over_long:
        return None
    return (
        FINDING_SEPARATOR.join(each_violation for each_violation, _ in all_over_long),
        CARD_TEXT_SEPARATOR.join(each_text for _, each_text in all_over_long),
    )


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
    checked = github_comment_violation(tool_name, tool_input) or tool_violation(
        tool_name, tool_input, hook_input.get(TRANSCRIPT_PATH_KEY)
    )
    if checked is None:
        write_flowchart_advice(tool_name, tool_input)
        return ALLOW_EXIT_CODE
    violation, reply_text = checked
    numbered_violation = numbered_violations(violation)
    instruction = RETRY_INSTRUCTION + FIX_EVERY_ITEM_INSTRUCTION
    block_reason = (
        numbered_violation + FINDING_SEPARATOR + instruction.lstrip()
        if FINDING_SEPARATOR in numbered_violation
        else numbered_violation + instruction
    )
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
