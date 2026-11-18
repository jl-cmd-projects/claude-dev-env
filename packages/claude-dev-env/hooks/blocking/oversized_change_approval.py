"""Tell whether the user typed, in this session, that one oversized pull request stays whole.

::

    user types "keep it as one PR, that's approved"              -> approved
    user types "don't split it"                                  -> approved
    user types "split that, it is way too big for one PR"        -> not approved
    user types "approved" or "is this one pull request?"         -> not approved
    user types "the size gate allows it if the user approved"    -> not approved
    the same words in an assistant message or a tool result      -> not approved
    relay message, the words inside <cited author="user">        -> approved
    relay message, the words only in the agent's <note>          -> not approved

A sentence counts when it holds an approval or keep-whole phrase and a size
subject, with no negation and no request to split. "Do not split it" holds
both parts on its own, when it, this, that or the pull request ends the clause.
A sentence that ends in a question mark never counts. A sentence that holds
"if", "whether", "unless", "until", "gate", "rule", "but", "yet", "said" or
"depends" states a condition or describes the rule, so it never counts either.
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
    ALL_SKIPPED_RECORD_FLAGS,
    APPROVAL_PATTERN,
    CITED_USER_TEXT_PATTERN,
    CONTENT_KEY,
    CURLY_APOSTROPHE,
    KEEP_WHOLE_PATTERN,
    LEADING_TAG_PATTERN,
    MESSAGE_KEY,
    META_RECORD_FLAG,
    NEGATION_PATTERN,
    QUESTION_MARK,
    RECORD_TYPE_KEY,
    RELAY_WRAPPER_PATTERN,
    RULE_TALK_PATTERN,
    ROLE_KEY,
    SENTENCE_BREAK_PATTERN,
    SIZE_SUBJECT_PATTERN,
    SPLIT_WORD_PATTERN,
    STRAIGHT_APOSTROPHE,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    USER_ROLE,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING


def has_user_approved_oversized_pull_request(transcript_path: object) -> bool:
    """Return True when a message the user typed in the transcript approves one large pull request.

    A transcript that is missing or cannot be read holds no approval.

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
            return any(
                is_size_approval(each_text)
                for each_line in all_lines
                for each_text in _user_typed_texts(each_line)
            )
    except OSError:
        return False


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
    normalized_text = message_text.lower().replace(CURLY_APOSTROPHE, STRAIGHT_APOSTROPHE)
    return any(
        _is_approving_sentence(each_sentence.strip())
        for each_sentence in SENTENCE_BREAK_PATTERN.split(normalized_text)
    )


def _is_approving_sentence(sentence: str) -> bool:
    if not sentence or sentence.endswith(QUESTION_MARK):
        return False
    if RULE_TALK_PATTERN.search(sentence):
        return False
    if KEEP_WHOLE_PATTERN.search(sentence):
        return True
    if NEGATION_PATTERN.search(sentence) or SPLIT_WORD_PATTERN.search(sentence):
        return False
    return bool(APPROVAL_PATTERN.search(sentence) and SIZE_SUBJECT_PATTERN.search(sentence))


def _user_typed_texts(transcript_line: str) -> Iterator[str]:
    all_record_fields = parsed_object(transcript_line)
    if all_record_fields is None or USER_ROLE != all_record_fields.get(RECORD_TYPE_KEY):
        return
    message_body = all_record_fields.get(MESSAGE_KEY)
    if not isinstance(message_body, dict) or message_body.get(ROLE_KEY) != USER_ROLE:
        return
    if any(all_record_fields.get(each_flag) for each_flag in ALL_SKIPPED_RECORD_FLAGS):
        return
    all_block_texts = _block_texts(message_body.get(CONTENT_KEY))
    if all_block_texts is None:
        return
    if any(RELAY_WRAPPER_PATTERN.search(each_text) for each_text in all_block_texts):
        for each_text in all_block_texts:
            yield from CITED_USER_TEXT_PATTERN.findall(each_text)
        return
    if all_record_fields.get(META_RECORD_FLAG):
        return
    yield from (
        each_text for each_text in all_block_texts if not LEADING_TAG_PATTERN.match(each_text)
    )


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
