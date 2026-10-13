"""Constants for the gate that keeps merge-over-review offers off decision cards."""

import re

TOOL_INPUT_KEY = "tool_input"
HOOK_EVENT_NAME = "PreToolUse"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
ALL_CARD_TEXT_FIELDS = ("question", "header", "context", "reason")
QUESTIONS_FIELD = "questions"
OPTIONS_FIELD = "options"
TEXT_SEPARATOR = " "
ALL_OPTION_TEXT_FIELDS = ("label", "consequence", "description")
MERGE_OFFER_PATTERN = re.compile(
    r"\b(?:merg(?:e|es|ing)|squash(?:es|ing)?|auto-merge)\b"
    r"(?!\s+(?:review|check|base|conflicts?|state|status|gate)\b)",
    re.IGNORECASE,
)
CLEAN_REVIEW_PATTERN = re.compile(
    r"\b(?:no|zero|0)\s+(?:open\s+|review\s+|blocking\s+)?(?:findings?|failures?|threads?|comments?)\b",
    re.IGNORECASE,
)
OPEN_REVIEW_PATTERN = re.compile(
    r"\b(?:findings?|override|red|failing|failed|failures?|not clean|unresolved|unaddressed"
    r"|changes requested|review comments?|open (?:review )?threads?|issues? (?:left|remain(?:ing)?)"
    r"|\d+ remaining)\b",
    re.IGNORECASE,
)
MERGE_OVER_REVIEW_OFFER_REASON = (
    "This card offers a merge while it names open review findings, a red check, or an"
    " override. A pull request merges only after a review pass on its head reports zero"
    " findings. Drop the merge offer, keep fixing and rerunning the review, and ask only"
    " about choices that keep that bar."
)
