"""Vocabulary for the controller and service receipts."""

ALL_APPROVAL_TEXT_BY_STATUS = {"active": "Approval is active", "pending": "Approval is pending"}
ALL_OPERATIONS = {"read", "capability", "write", "message", "unsupported", "operator_status"}
ALL_PUBLICATION_CHECKS = {"capability", "write"}
ALL_NOTICE_CRITERIA = ("error_clear", "least_scope_ask", "impact_clear")
ALL_MESSAGE_FIELDS = ("recipient", "body", "seq", "elapsed_ms")
ALL_REVIEW_ATTRIBUTION_FIELDS = ("reviewer", "reason")
ALL_LAUNCH_DIGEST_FIELDS = ("order_sha256", "instructions_sha256")
ALL_RECORD_OPERATIONS = {"read", "write"}
TARGET_BOUNDARY_PATTERN = r"(?<![\w/-]){}(?![\w/-])"
HOSTED_MODEL = "gpt-6.2-sol"
HOSTED_EFFORT = "high"
HOSTED_HANDLE_PREFIX = "/root/"
HOSTED_COMPLETION_TYPE = "FINAL_ANSWER"
HOSTED_LAUNCH_TOOL = "collaboration.spawn_agent"
HOSTED_FOLLOWUP_TOOL = "collaboration.followup_task"
EXPECTED_TURN_COUNT = 2
