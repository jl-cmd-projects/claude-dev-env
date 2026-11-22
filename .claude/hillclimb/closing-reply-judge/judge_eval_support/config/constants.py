"""Configuration for the closing-reply judge eval."""

from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FLOW_ROOT.parents[2]
HOOKS_DIRECTORY = REPOSITORY_ROOT / "packages" / "claude-dev-env" / "hooks"
BLOCKING_DIRECTORY = HOOKS_DIRECTORY / "blocking"
CASES_FILE = FLOW_ROOT / "cases.json"
JSON_LIST_SUFFIX = ".json"
CALL_LOG_FILE_NAME = "results.jsonl"
DEFAULT_OUT_DIRECTORY = FLOW_ROOT / "v1"
DEFAULT_MODEL = "haiku"
DEFAULT_EFFORT = "medium"
DEFAULT_RUNS = 3
DEFAULT_WORKERS = 6
DEFAULT_ATTEMPTS = 3
MODEL_FLAG = "--model"
EFFORT_FLAG = "--effort"
TEXT_ENCODING = "utf-8"
DECODE_ERRORS = "replace"
DIGEST_LENGTH = 16
SECONDS_DECIMALS = 2
NINETIETH_PERCENTILE = 0.9
STATUS_OK = "ok"
STATUS_SHAPE = "shape"
STATUS_ERROR = "error"
ALL_SCORED_STATUSES = (STATUS_OK, STATUS_SHAPE)
TIMEOUT_ERROR = "timeout"
START_FAILURE_ERROR = "start failure"
EXIT_CODE_ERROR_TEMPLATE = "exit code {exit_code}"
NOT_JSON_ERROR = "stdout is not JSON"
IS_ERROR_ERROR = "is_error"
ANSWER_RESULT_KEY = "result"
ANSWER_IS_ERROR_KEY = "is_error"
ANSWER_COST_KEY = "total_cost_usd"
ANSWER_MODEL_USAGE_KEY = "modelUsage"
PASS_LABEL = "pass"
PROMISE_FLAG_INDEX = 0
LIST_FLAG_INDEX = 1
ALL_NEEDED_FLAG_INDEXES = {
    "hold-promise": (PROMISE_FLAG_INDEX,),
    "hold-list": (LIST_FLAG_INDEX,),
    "hold-both": (PROMISE_FLAG_INDEX, LIST_FLAG_INDEX),
}
CASE_ID_SEPARATOR = "/"
SEPARATE_PASS_SET = "heldout_v3"
ALL_INCIDENT_TWIN_IDS = ("twins/INC1", "twins/INC2")
FAULT_HELD_SHARE_BAR = 0.95
OTHER_PASS_WRONG_HOLD_BAR = 1
SEPARATE_PASS_WRONG_HOLD_BAR = 3
MAIN_STOP_WRONG_HOLD_BAR = 2
EVAL_BARS = "eval"
MAIN_STOP_BARS = "main"
ALL_BAR_CHOICES = (EVAL_BARS, MAIN_STOP_BARS)
PASSED_PREFIX = "PASS "
MISSED_PREFIX = "MISS "
NO_CLAUDE_MESSAGE = "no claude on PATH"
ALL_DIGEST_SOURCES = (
    BLOCKING_DIRECTORY / "closing_reply_judge.py",
    BLOCKING_DIRECTORY / "closing_reply_shapes.py",
    BLOCKING_DIRECTORY / "closing_question_round_footer.py",
    BLOCKING_DIRECTORY / "closing_question_round_open_items.py",
    HOOKS_DIRECTORY / "hooks_constants" / "closing_question_round_gate_constants.py",
    HOOKS_DIRECTORY / "hooks_constants" / "closing_reply_judge_constants.py",
)
