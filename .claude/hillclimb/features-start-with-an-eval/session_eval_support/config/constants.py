"""Configuration for the features-start-with-an-eval session eval."""

from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FLOW_ROOT.parents[2]
FIXTURE_DIRECTORY = FLOW_ROOT / "fixture"
CASES_FILE = FLOW_ROOT / "cases.json"
STATE_FILE = FLOW_ROOT / "_state.json"
BROKER_SCRIPT = Path.home() / ".claude" / "scripts" / "account_broker.py"
RESULTS_FILE_NAME = "results.jsonl"
ERRORS_FILE_NAME = "errors.jsonl"
TRACES_DIRECTORY_NAME = "traces"
TRACE_FILE_TEMPLATE = "{case_id}_rep{rep}.json"
STREAM_FILE_NAME = "stream.jsonl"
BROKER_REPORT_FILE_NAME = "broker-report.json"
WORKSPACE_PREFIX = "features-eval-"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TURNS = 6
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_REPS = 1
DEFAULT_PARALLEL = 2
BROKER_WAIT_EXIT_CODE = 3
EXPECTED_BUILD_EVAL = "build-eval"
EXPECTED_NONE = "none"
BUILD_EVAL_SKILL_NAME = "claude-api"
BUILD_EVAL_ARGUMENT_WORD = "build-eval"
LOCAL_BUILD_EVAL_SKILL_NAME = "build-eval"
PLUGIN_SEPARATOR = ":"
SKILL_TOOL_NAME = "Skill"
ALL_EDIT_OR_SPAWN_TOOL_NAMES = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Task"}
)
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
TEXT_BLOCK_TYPE = "text"
ASSISTANT_EVENT_TYPE = "assistant"
USER_EVENT_TYPE = "user"
RESULT_EVENT_TYPE = "result"
SUCCESS_SUBTYPE = "success"
MAX_TURNS_SUBTYPE = "error_max_turns"
ALL_SCORABLE_SUBTYPES = frozenset({SUCCESS_SUBTYPE, MAX_TURNS_SUBTYPE})
STATUS_OK = "ok"
FAILURE_TIMEOUT = "timeout"
FAILURE_BROKER_WAIT = "broker-wait"
FAILURE_NO_RESULT = "no-result"
FAILURE_MODEL_MISMATCH = "served-model-mismatch"
JSON_INDENT = 2
LATENCY_DECIMALS = 1
MILLISECONDS_PER_SECOND = 1000
WILSON_Z = 1.96
WILSON_Z_SQUARED = WILSON_Z**2
WILSON_CENTER_DIVISOR = 2
WILSON_SPREAD_DIVISOR = 4
TOOL_RESULT_PREVIEW_LENGTH = 2000
FIRST_TOOLS_PER_TURN = 2
NEWLINE = "\n"
ALL_GIT_INIT_COMMANDS = (
    ("git", "init", "-q", "-b", "main"),
    ("git", "add", "-A"),
    (
        "git",
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        "fixture",
    ),
)
