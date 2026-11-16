"""Configuration for the closing question round gate eval."""

from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FLOW_ROOT.parents[2]
CASES_FILE = FLOW_ROOT / "cases.json"
HOOK_FILE = (
    REPOSITORY_ROOT
    / "packages"
    / "claude-dev-env"
    / "hooks"
    / "blocking"
    / "closing_question_round_gate.py"
)

CASE_ID_KEY = "id"
CASE_EXPECTED_KEY = "expected"
CASE_TRANSCRIPT_KEY = "transcript"
CASE_PAYLOAD_KEY = "payload"
CASE_ENVIRONMENT_KEY = "environment"

HOLD_DECISION = "hold"
ALLOW_DECISION = "allow"
UNREADABLE_DECISION = "unreadable"
HOLD_EXIT_CODE = 2
ALLOW_EXIT_CODE = 0
STOP_DECISION_KEY = "decision"
STOP_BLOCK_DECISION = "block"

TRANSCRIPT_FILE_NAME = "transcript.jsonl"
HOME_DIRECTORY_NAME = "home"
RECORD_SEPARATOR = "\n"
UTF8_ENCODING = "utf-8"
HOOK_TIMEOUT_SECONDS = 10
ALL_HOME_ENVIRONMENT_VARIABLES = ("HOME", "USERPROFILE")
SESSION_ATTENDED_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_SESSION_ATTENDED"
INTERACTIVE_SESSION_ATTENDED_TEXT = "1"
TRANSCRIPT_PATH_KEY = "transcript_path"
ALL_BASE_PAYLOAD_FIELDS = {
    "hook_event_name": "Stop",
    "session_id": "eval-session",
    "stop_hook_active": False,
}

PASSED_ROW_LABEL = "ok"
MISSED_ROW_LABEL = "MISS"
ROW_TEMPLATE = "{label:<4} {case_id}: expected {expected}, got {decision}"
SUMMARY_TEMPLATE = "passed {passed_count}/{case_count}"
MISSED_EXIT_CODE = 1
PASSED_EXIT_CODE = 0
