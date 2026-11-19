"""Tell whether the user typed, in this session, that one oversized pull request stays whole.

::

    user types "keep it as one PR, that's approved"              -> approved
    user types "don't split it"                                  -> approved
    user types "split that, it is way too big for one PR"        -> not approved
    user types "approved" or "is this one pull request?"         -> not approved
    user types "the size gate allows it if the user approved"    -> not approved
    user approves, then later types "split it after all"         -> not approved
    user types 'add a test for "don't split it"'                 -> not approved
    user types "I revoke my approval to keep it as one PR"       -> not approved
    the user's message was queued while a turn ran               -> read like a typed one
    a peer agent's message holds the approving words             -> not approved
    the same words in an assistant message or a tool result      -> not approved
    relay message, the words inside <cited author="user">        -> approved
    relay message, the words only in the agent's <note>          -> not approved

A sentence counts when it holds an approval or keep-whole phrase and a size
subject, with no negation and no request to split. "Do not split it" holds
both parts on its own, when it, this, that or the pull request ends the clause.
A sentence that ends in a question mark never counts. A sentence that holds
"if", "whether", "unless", "until", "gate", "rule", "but", "yet", "said" or
"depends" states a condition or describes the rule, so it never counts either.
A sentence that holds a double quote cites words, so it never counts. Revoke,
withdraw, retract and cancel negate like "not".
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.gate_run_reads import ReadSlice, transcript_lines_within_slice
from blocking.open_tasks_transcript_records import parsed_object
from hooks_constants.oversized_change_constants import (
    ALL_RELAY_ORIGIN_KINDS,
    ALL_SKIPPED_RECORD_FLAGS,
    ALL_TYPED_ORIGIN_KINDS,
    ATTACHMENT_KEY,
    ATTACHMENT_RECORD_TYPE,
    APPROVAL_PATTERN,
    CITED_USER_TEXT_PATTERN,
    CONTENT_KEY,
    CURLY_APOSTROPHE,
    DOUBLE_QUOTE,
    KEEP_WHOLE_PATTERN,
    LEADING_TAG_PATTERN,
    MESSAGE_KEY,
    META_RECORD_FLAG,
    NEGATION_PATTERN,
    ORIGIN_KEY,
    QUEUED_COMMAND_TYPE,
    QUEUED_PROMPT_KEY,
    ORIGIN_KIND_KEY,
    QUESTION_MARK,
    RECORD_TYPE_KEY,
    RELAY_WRAPPER_PATTERN,
    RULE_TALK_PATTERN,
    ROLE_KEY,
    SENTENCE_BREAK_PATTERN,
    SIZE_SUBJECT_PATTERN,
    SPLIT_WORD_PATTERN,
    STRAIGHT_APOSTROPHE,
    TEXT_BLOCK_JOINER,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    USER_ROLE,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING


def has_user_approved_oversized_pull_request(transcript_path: object) -> bool:
    """Return True when the newest size verdict the user typed approves one large pull request.

    The scan reads newest first and stops at the first message that approves or
    asks for a split. A transcript that is missing or cannot be read holds no approval.

    Args:
        transcript_path: The ``transcript_path`` the hook payload names.
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return False
    try:
        with open(transcript_path, "rb") as transcript:
            all_lines = transcript_lines_within_slice(
                transcript, UTF8_ENCODING, DECODE_ERRORS_POLICY, ReadSlice.PROOF_AND_LOOK
            )
            all_verdicts = (
                size_verdict(each_text)
                for each_line in all_lines
                for each_text in _user_typed_texts(each_line)
            )
            return next(
                (each_verdict for each_verdict in all_verdicts if each_verdict is not None), False
            )
    except OSError:
        return False


def size_verdict(message_text: str) -> bool | None:
    """Return False for a message that asks for a split, True for one that approves, else None.

    ::

        "keep it as one PR, that's approved"        -> True
        "split it after all"                        -> False
        "approved as one PR. then, split it"        -> False
        "don't split hairs"                         -> None
        "run the tests"                             -> None

    Args:
        message_text: The text of one message the user typed.
    """
    if any(_is_split_request(each_sentence) for each_sentence in _sentences(message_text)):
        return False
    return True if is_size_approval(message_text) else None


def is_size_approval(message_text: str) -> bool:
    """Return True when one sentence of the text approves keeping one large pull request.

    ::

        "I approve this as one pull request"        -> True
        "the size is fine for this pull request"   -> True
        "do not split this pull request"            -> True
        "not approved over the size bar"            -> False
        "is this one pull request?"                 -> False

    Args:
        message_text: The text of one message the user typed.
    """
    return any(_is_approving_sentence(each_sentence) for each_sentence in _sentences(message_text))


def _sentences(message_text: str) -> list[str]:
    normalized_text = message_text.lower().replace(CURLY_APOSTROPHE, STRAIGHT_APOSTROPHE)
    return [each_sentence.strip() for each_sentence in SENTENCE_BREAK_PATTERN.split(normalized_text)]


def _is_split_request(sentence: str) -> bool:
    if sentence.endswith(QUESTION_MARK) or NEGATION_PATTERN.search(sentence):
        return False
    return bool(SPLIT_WORD_PATTERN.search(sentence))


def _is_approving_sentence(sentence: str) -> bool:
    if not sentence or sentence.endswith(QUESTION_MARK):
        return False
    if RULE_TALK_PATTERN.search(sentence) or DOUBLE_QUOTE in sentence:
        return False
    if KEEP_WHOLE_PATTERN.search(sentence):
        return True
    if NEGATION_PATTERN.search(sentence) or SPLIT_WORD_PATTERN.search(sentence):
        return False
    return bool(APPROVAL_PATTERN.search(sentence) and SIZE_SUBJECT_PATTERN.search(sentence))


def _user_typed_texts(transcript_line: str) -> Iterator[str]:
    all_record_fields = parsed_object(transcript_line)
    if all_record_fields is None:
        return
    if any(all_record_fields.get(each_flag) for each_flag in ALL_SKIPPED_RECORD_FLAGS):
        return
    all_source_fields = _message_source_fields(all_record_fields)
    if all_source_fields is None:
        return
    all_block_texts, all_origin_fields = all_source_fields
    origin = all_origin_fields.get(ORIGIN_KEY)
    origin_kind = origin.get(ORIGIN_KIND_KEY) if isinstance(origin, dict) else None
    if any(RELAY_WRAPPER_PATTERN.search(each_text) for each_text in all_block_texts):
        if origin_kind in ALL_RELAY_ORIGIN_KINDS:
            yield from _cited_user_texts(all_block_texts)
        return
    if all_origin_fields.get(META_RECORD_FLAG) or origin_kind not in ALL_TYPED_ORIGIN_KINDS:
        return
    yield TEXT_BLOCK_JOINER.join(
        each_text for each_text in all_block_texts if not LEADING_TAG_PATTERN.match(each_text)
    )


def _message_source_fields(
    all_record_fields: dict[str, object],
) -> tuple[list[str], dict[str, object]] | None:
    record_type = all_record_fields.get(RECORD_TYPE_KEY)
    if record_type == ATTACHMENT_RECORD_TYPE:
        attachment = all_record_fields.get(ATTACHMENT_KEY)
        if not isinstance(attachment, dict):
            return None
        queued_prompt = attachment.get(QUEUED_PROMPT_KEY)
        if attachment.get(RECORD_TYPE_KEY) != QUEUED_COMMAND_TYPE or not isinstance(queued_prompt, str):
            return None
        return [queued_prompt], attachment
    message_body = all_record_fields.get(MESSAGE_KEY)
    if record_type != USER_ROLE or not isinstance(message_body, dict):
        return None
    all_block_texts = _block_texts(message_body.get(CONTENT_KEY))
    if message_body.get(ROLE_KEY) != USER_ROLE or all_block_texts is None:
        return None
    return all_block_texts, all_record_fields


def _cited_user_texts(all_block_texts: list[str]) -> Iterator[str]:
    for each_text in all_block_texts:
        yield from CITED_USER_TEXT_PATTERN.findall(each_text)


def _block_texts(content: object) -> list[str] | None:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return None
    all_blocks = [each_block for each_block in content if isinstance(each_block, dict)]
    if any(each_block.get(RECORD_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE for each_block in all_blocks):
        return None
    return [
        each_block[TEXT_KEY]
        for each_block in all_blocks
        if each_block.get(RECORD_TYPE_KEY) == TEXT_BLOCK_TYPE
        and isinstance(each_block.get(TEXT_KEY), str)
    ]
