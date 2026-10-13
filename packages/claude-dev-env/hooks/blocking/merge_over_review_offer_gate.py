"""Deny a decision card that offers a merge over open review findings."""

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
    ALL_CARD_TEXT_FIELDS,
    ALL_OPTION_TEXT_FIELDS,
    MERGE_OFFER_PATTERN,
    MERGE_OVER_REVIEW_OFFER_REASON,
    OPEN_REVIEW_PATTERN,
    OPTIONS_FIELD,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    DENY_DECISION,
    HOOK_EVENT_NAME,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


def _option_texts(tool_input: dict[str, object]) -> list[str]:
    all_options = tool_input.get(OPTIONS_FIELD)
    if not isinstance(all_options, list):
        return []
    return [
        " ".join(str(each_option.get(each_field, "")) for each_field in ALL_OPTION_TEXT_FIELDS)
        for each_option in all_options
        if isinstance(each_option, dict)
    ]


def offers_merge_over_review(tool_input: dict[str, object]) -> bool:
    """Return whether a decision card offers a merge while it names open review findings.

    ::

        option "Merge now", context "9 findings remain"     -> True
        option "Merge now", consequence "override the red"  -> True
        option "Keep looping", context "9 findings remain"  -> False
        option "Merge", context "review pass was clean"     -> False

    Args:
        tool_input: The decision card's tool input.
    """
    all_option_texts = _option_texts(tool_input)
    if not any(MERGE_OFFER_PATTERN.search(each_text) for each_text in all_option_texts):
        return False
    card_text = " ".join(
        [str(tool_input.get(each_field, "")) for each_field in ALL_CARD_TEXT_FIELDS]
        + all_option_texts
    )
    return OPEN_REVIEW_PATTERN.search(card_text) is not None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a card that offers a merge over open findings, else None.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_input, dict) or not offers_merge_over_review(tool_input):
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
