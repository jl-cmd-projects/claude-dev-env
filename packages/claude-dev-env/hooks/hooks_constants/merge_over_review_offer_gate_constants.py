"""Constants for the gate that keeps merge-over-review offers off decision cards."""

import re

ALL_OFFER_TEXT_FIELDS = ("question", "header")
ALL_STATE_TEXT_FIELDS = ("context", "reason")
QUESTIONS_FIELD = "questions"
OPTIONS_FIELD = "options"
TEXT_SEPARATOR = " "
ALL_OPTION_TEXT_FIELDS = ("label", "consequence", "description")
MERGE_OFFER_PATTERN = re.compile(
    r"\b(?:merg(?:e|es|ing)|land(?:s|ing)?|ship(?:s|ping)?|squash(?:es|ing)?)\b"
    r"(?!\s+(?:review|check|queue|base|conflicts?|state|status|gate)\b)",
    re.IGNORECASE,
)
CLEAN_REVIEW_PATTERN = re.compile(
    r"\b(?:no|zero|0)\s+(?:open\s+|review\s+|blocking\s+)?(?:findings?|failures?|threads?)\b",
    re.IGNORECASE,
)
OPEN_REVIEW_PATTERN = re.compile(
    r"\b(?:findings?|override|red|failing|failed|failures?|not clean|unresolved|blocking"
    r"|pending|open (?:review )?threads?)\b",
    re.IGNORECASE,
)
MERGE_OVER_REVIEW_OFFER_REASON = (
    "This card offers a merge while it names open review findings, a red or pending"
    " check, or an override. A pull request merges only after a review pass on its head"
    " reports zero findings. Drop the merge offer, keep fixing and rerunning the review,"
    " and ask only about choices that keep that bar."
)
