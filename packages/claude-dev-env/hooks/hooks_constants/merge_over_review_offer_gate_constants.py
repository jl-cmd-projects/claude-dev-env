"""Constants for the gate that keeps merge-over-review options off decision cards."""

import re

ALL_CARD_TEXT_FIELDS = ("question", "context", "reason")
OPTIONS_FIELD = "options"
TEXT_SEPARATOR = " "
ALL_OPTION_TEXT_FIELDS = ("label", "consequence")
MERGE_OFFER_PATTERN = re.compile(r"\bmerge\b", re.IGNORECASE)
OPEN_REVIEW_PATTERN = re.compile(
    r"\b(?:findings?|override|red|failing|failures?|not clean)\b", re.IGNORECASE
)
MERGE_OVER_REVIEW_OFFER_REASON = (
    "This decision card offers a merge while the card names open review findings or a red"
    " check. A pull request merges only after a review pass on its head reports zero"
    " findings. Drop the merge option, keep fixing and rerunning the review, and ask only"
    " about choices that keep that bar."
)
