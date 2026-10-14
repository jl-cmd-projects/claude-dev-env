"""Constants for the plain-wording judge eval."""

import re
from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
HOOKS_CONFIG_PATH = FLOW_ROOT.parents[2] / "packages" / "claude-dev-env" / "hooks" / "hooks.json"
CASES_PATH = FLOW_ROOT / "cases.json"
JUDGE_STATUS_MESSAGE = "claude-dev-env: checking the message against Jon's writing rules"
REPLY_TOOL_NAME = "mcp__hearthbot__reply"
ARGUMENTS_PLACEHOLDER = "$ARGUMENTS"
JUDGE_MODEL = "haiku"
HELD_OUT_SPLIT = "held_out"
FAIL_LABEL = "fail"
VERDICT_PATTERN = re.compile(r'"ok"\s*:\s*(true|false)')
DENIED_VERDICT = "false"
CALL_TIMEOUT_SECONDS = 120
DEFAULT_WORKER_COUNT = 8
ROW_SEPARATOR = "\n"
