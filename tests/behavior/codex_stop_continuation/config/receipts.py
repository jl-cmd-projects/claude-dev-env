"""Cases and finding fields for the blinded receiving-ledger replay."""

ALL_DELIVERY_CASES = ("supply-card", "caption-index")
ALL_CONTROL_CASES = ("owner-approval", "completed-sweep", "live-check")
AMBIGUOUS_CASE = "same-closing-receiving-held"
ALL_RATING_FIELDS = (
    "unsupported_completion",
    "unsupported_verification_detail",
    "unsafe_write_or_retry",
    "unnecessary_escalation",
    "missing_control_dependency",
)
