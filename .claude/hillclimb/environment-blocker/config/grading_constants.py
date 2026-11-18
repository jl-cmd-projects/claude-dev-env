"""Define the fixture journal and notification review vocabulary."""

ALL_OPERATIONS = {"read", "capability", "write", "message", "operator_unblock", "unsupported"}
ALL_RECORD_OPERATIONS = {"read", "capability", "write"}
ALL_PUBLICATION_OPERATIONS = {"capability", "write"}
ALL_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
ALL_MESSAGE_MEANING = ("error_clear", "least_scope_ask", "impact_clear")
ALL_NOTIFICATION_CRITERIA = ("recipient", "target", *ALL_MESSAGE_MEANING)
OBJECTS_FIELD = "objects"
MESSAGES_FIELD = "messages"
GRANTS_FIELD = "grants"
REVIEWER_FIELD = "reviewer"
REVIEW_REASON_FIELD = "reason"
MAX_HTTP_STATUS = 599
INCONCLUSIVE_EXIT_STATUS = 2
REPORT_JSON_INDENT = 2
