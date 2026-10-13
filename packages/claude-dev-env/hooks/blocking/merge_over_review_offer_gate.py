"""Deny a decision card or question that offers a merge over open review findings."""

from __future__ import annotations

import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.merge_over_review_offer_gate_constants import (
    ALL_OFFER_TEXT_FIELDS,
    ALL_OPTION_TEXT_FIELDS,
    ALL_STATE_TEXT_FIELDS,
    CLEAN_REVIEW_PATTERN,
    MERGE_OFFER_PATTERN,
    MERGE_OVER_REVIEW_OFFER_REASON,
    OPEN_REVIEW_PATTERN,
    OPTIONS_FIELD,
    QUESTIONS_FIELD,
    TEXT_SEPARATOR,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    DENY_DECISION,
    HOOK_EVENT_NAME,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


def _one_option_text(each_option: object) -> str:
    if isinstance(each_option, dict):
        return TEXT_SEPARATOR.join(
            str(each_option.get(each_field, "")) for each_field in ALL_OPTION_TEXT_FIELDS
        )
    return str(each_option)


def _option_texts(all_question_fields: dict[str, object]) -> list[str]:
    all_options = all_question_fields.get(OPTIONS_FIELD)
    if not isinstance(all_options, list):
        return []
    return [_one_option_text(each_option) for each_option in all_options]


def _field_texts(all_fields: dict[str, object], all_field_names: tuple[str, ...]) -> list[str]:
    return [str(all_fields.get(each_field, "")) for each_field in all_field_names]


def _question_blocks(all_card_fields: dict[str, object]) -> list[dict[str, object]]:
    all_questions = all_card_fields.get(QUESTIONS_FIELD)
    if isinstance(all_questions, list):
        return [each_question for each_question in all_questions if isinstance(each_question, dict)]
    return [all_card_fields]


def _question_offers_merge_over_review(
    all_question_fields: dict[str, object], all_state_texts: list[str]
) -> bool:
    all_offer_texts = _field_texts(all_question_fields, ALL_OFFER_TEXT_FIELDS) + _option_texts(
        all_question_fields
    )
    if not any(MERGE_OFFER_PATTERN.search(each_text) for each_text in all_offer_texts):
        return False
    card_text = TEXT_SEPARATOR.join(all_offer_texts + all_state_texts)
    return OPEN_REVIEW_PATTERN.search(CLEAN_REVIEW_PATTERN.sub("", card_text)) is not None


def offers_merge_over_review(all_card_fields: dict[str, object]) -> bool:
    """Return whether a card offers a merge while it names open review findings.

    The offer is read from the question and the options. The review state is
    read from those and from the context and reason. Both card shapes count:
    an ``ask_decision`` card and an ``AskUserQuestion`` questions list.

    ::

        option "Merge now", context "9 findings remain"         -> True
        question "Merge PR 41 now?", options "Yes" / "No",
            context "3 unresolved threads"                      -> True
        option "Keep looping", context "9 findings remain"      -> False
        context "The merge review check reports 11 findings",
            options "Keep fixing" / "Split it"                  -> False
        option "Merge", context "the review found no findings"  -> False

    Args:
        all_card_fields: The card's tool input.
    """
    all_state_texts = _field_texts(all_card_fields, ALL_STATE_TEXT_FIELDS)
    return any(
        _question_offers_merge_over_review(each_question, all_state_texts)
        for each_question in _question_blocks(all_card_fields)
    )


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a card that offers a merge over open findings, else None.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    all_card_fields = all_payload_fields.get("tool_input")
    if not isinstance(all_card_fields, dict) or not offers_merge_over_review(all_card_fields):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: MERGE_OVER_REVIEW_OFFER_REASON,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
