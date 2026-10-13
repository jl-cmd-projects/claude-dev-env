"""Deny a decision card or question that offers a merge over open review findings."""

from __future__ import annotations

import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.merge_over_review_offer_gate_constants import (
    ALL_CARD_TEXT_FIELDS,
    ALL_OPTION_TEXT_FIELDS,
    CLEAN_REVIEW_PATTERN,
    DENY_DECISION,
    HOOK_EVENT_NAME,
    MERGE_OFFER_PATTERN,
    MERGE_OVER_REVIEW_OFFER_REASON,
    OPEN_REVIEW_PATTERN,
    OPTIONS_FIELD,
    PERMISSION_DECISION_REASON_KEY,
    QUESTIONS_FIELD,
    TEXT_SEPARATOR,
    TOOL_INPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


def _one_option_text(each_option: object) -> str:
    if isinstance(each_option, dict):
        return TEXT_SEPARATOR.join(
            str(each_option.get(each_field, "")) for each_field in ALL_OPTION_TEXT_FIELDS
        )
    return str(each_option)


def _block_texts(block_by_key: dict[str, object]) -> list[str]:
    all_texts = [str(block_by_key.get(each_field, "")) for each_field in ALL_CARD_TEXT_FIELDS]
    all_options = block_by_key.get(OPTIONS_FIELD)
    if isinstance(all_options, list):
        all_texts.extend(_one_option_text(each_option) for each_option in all_options)
    return all_texts


def _card_text(card_by_key: dict[str, object]) -> str:
    all_questions = card_by_key.get(QUESTIONS_FIELD)
    if not isinstance(all_questions, list):
        all_questions = []
    all_blocks = [card_by_key] + [
        each_question for each_question in all_questions if isinstance(each_question, dict)
    ]
    return TEXT_SEPARATOR.join(
        each_text for each_block in all_blocks for each_text in _block_texts(each_block)
    )


def offers_merge_over_review(card_by_key: dict[str, object]) -> bool:
    """Return whether a card offers a merge while it names open review findings.

    The whole card is read as one text: every question, header, context,
    reason, and option, across both card shapes, an ``ask_decision`` card and
    an ``AskUserQuestion`` questions list.

    ::

        option "Merge now", context "9 findings remain"          -> True
        question 1 "The review reports 9 findings.",
            question 2 "Merge it now?" with "Yes" / "No"         -> True
        context "I can merge it now, but 9 findings remain."     -> True
        option "Join the merge queue", context "9 findings"      -> True
        context "The merge review check reports 11 findings",
            options "Keep fixing" / "Split it"                   -> False
        option "Merge", context "the review found no findings"   -> False

    Args:
        card_by_key: The card's tool input.
    """
    card_text = _card_text(card_by_key)
    if not MERGE_OFFER_PATTERN.search(card_text):
        return False
    return OPEN_REVIEW_PATTERN.search(CLEAN_REVIEW_PATTERN.sub("", card_text)) is not None


def decision_for(payload_by_key: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a card that offers a merge over open findings, else None.

    Args:
        payload_by_key: The parsed PreToolUse input.
    """
    card_by_key = payload_by_key.get(TOOL_INPUT_KEY)
    if not isinstance(card_by_key, dict) or not offers_merge_over_review(card_by_key):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: MERGE_OVER_REVIEW_OFFER_REASON,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
