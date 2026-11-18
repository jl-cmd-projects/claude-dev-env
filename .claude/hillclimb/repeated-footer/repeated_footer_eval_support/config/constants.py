"""Configuration for the repeated footer eval."""

import re
from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FLOW_ROOT.parents[2]
SCENARIO_FILE = FLOW_ROOT / "scenario.json"
HOOKS_DIRECTORY = REPOSITORY_ROOT / "packages" / "claude-dev-env" / "hooks"
ALL_STOP_GATE_FILE_NAMES = ("open_tasks_stop_gate.py", "closing_question_round_gate.py")
BLOCKING_DIRECTORY_NAME = "blocking"

UTF8_ENCODING = "utf-8"
RECORD_SEPARATOR = "\n"
LINE_BREAK = "\n"
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SPACE_RUN_PATTERN = re.compile(r"\s+")
SINGLE_SPACE = " "
MINIMUM_COUNTED_LINE_LENGTH = 16
FOOTER_HEADING_PATTERN = re.compile(
    r"^\s*(?:\*\*|__)?in progress:(?:\*\*|__)?\s*$", re.IGNORECASE
)
TOP_LINE_COUNT = 5

RECORD_TYPE_KEY = "type"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
ROLE_KEY = "role"
TEXT_KEY = "text"
TEXT_BLOCK_TYPE = "text"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
ASSISTANT_RECORD_TYPE = "assistant"
USER_RECORD_TYPE = "user"
TURN_ORIGIN_KEY = "turnOrigin"
HUMAN_TURN_ORIGIN = "human"
NOTIFICATION_TURN_ORIGIN = "task-notification"
NOTIFICATION_TEMPLATE = (
    "<task-notification><summary>{summary}</summary></task-notification>"
)
STOP_FEEDBACK_TEMPLATE = "Stop hook feedback:\n{reasons}"
TOOL_USE_ID_TEMPLATE = "toolu_{number:04d}"
TOOL_RESULT_TEXT = "ok"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"
READ_TOOL_NAME = "Bash"

SCENARIO_TASKS_KEY = "tasks"
SCENARIO_FOOTERS_KEY = "footers"
SCENARIO_TURNS_KEY = "turns"
TURN_KIND_KEY = "kind"
TURN_TEXT_KEY = "text"
TURN_TOOLS_KEY = "tools"
TURN_BODY_KEY = "body"
TURN_FOOTER_KEY = "footer"
TURN_TRACKER_BODY_KEY = "tracker_body"
TURN_READ_BODY_KEY = "read_body"
PROMPT_TURN_KIND = "prompt"
NOTIFICATION_TURN_KIND = "notification"
TASK_ID_KEY = "id"

MINIMAL_POLICY = "minimal"
LOGGED_POLICY = "logged"
ALL_POLICIES = (MINIMAL_POLICY, LOGGED_POLICY)

TRACKER_HOLD_TEXT = "left the task list unchanged"
LIST_HOLD_TEXT = "The closing reply lists"
ALL_FOOTER_HOLD_TEXTS = (
    "ended without the In progress footer",
    "footer leaves out work",
    "declared no open items",
)
MAXIMUM_HOLDS_PER_STOP = 4
HOLDS_UNCLEARED_TEMPLATE = "a turn was still held after {hold_count} stops; last hold: {lead}"

HOME_DIRECTORY_NAME = "home"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
TASKS_DIRECTORY_NAME = "tasks"
TASK_FILE_SUFFIX = ".json"
STUB_BIN_DIRECTORY_NAME = "bin"
STUB_JUDGE_FILE_NAME = "claude"
STUB_JUDGE_SOURCE = r"""#!/usr/bin/env python3
import json
import re
import sys

prompt_text = sys.stdin.read()
reply_match = re.search(r'"reply": ("(?:[^"\\]|\\.)*")', prompt_text)
reply_text = json.loads(reply_match.group(1)) if reply_match else ""
all_lines = reply_text.split("\n")
list_span = ""
for each_position, each_line in enumerate(all_lines):
    all_next_lines = all_lines[each_position + 1 : each_position + 4]
    if each_line.strip().endswith(":") and len(all_next_lines) == 3 and all(
        each_next.lstrip().startswith("- ") for each_next in all_next_lines
    ):
        list_span = each_line.strip()
        break
verdict = {
    "promised_report": False,
    "promise_span": "",
    "decisions_as_list": bool(list_span),
    "list_span": list_span,
}
sys.stdout.write(json.dumps({"result": json.dumps(verdict), "is_error": False}))
"""
STUB_JUDGE_MODE = 0o755
STUB_JUDGE_WINDOWS_FILE_NAME = "claude.cmd"
STUB_JUDGE_WINDOWS_TEMPLATE = '@"{python}" "%~dp0{script}" %*\r\n'
JUDGE_EXECUTABLE_NAME = "claude"
STUB_JUDGE_NOT_FIRST_TEMPLATE = "the stand-in judge in {stub_directory} is not the first claude on PATH: {found}"
ALLOW_EXIT_CODE = 0
GATE_START_FAILURE_TEMPLATE = "{gate} exited with code {exit_code}: {stderr_tail}"
STDERR_TAIL_LENGTH = 400
PATH_ENVIRONMENT_VARIABLE = "PATH"
ALL_HOME_ENVIRONMENT_VARIABLES = ("HOME", "USERPROFILE")
CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE = "CLAUDE_CONFIG_DIR"
ALL_REMOVED_ENVIRONMENT_VARIABLES = (
    "CLAUDE_CODE_TASK_LIST_ID",
    "CLAUDE_TURN_REVIEW_CHILD",
    "TMPDIR",
)
SESSION_ATTENDED_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_SESSION_ATTENDED"
INTERACTIVE_SESSION_ATTENDED_TEXT = "1"
TEMPORARY_DIRECTORY_ENVIRONMENT_VARIABLE = "TMPDIR"
TEMPORARY_DIRECTORY_NAME = "tmp"
SESSION_ID = "repeated-footer-eval"
TRANSCRIPT_FILE_NAME = "transcript.jsonl"
HOOK_TIMEOUT_SECONDS = 60
HOLD_EXIT_CODE = 2
STOP_REASON_KEY = "reason"
ALL_STOP_PAYLOAD_FIELDS = {
    "hook_event_name": "Stop",
    "session_id": SESSION_ID,
}
TRANSCRIPT_PATH_KEY = "transcript_path"
STOP_HOOK_ACTIVE_KEY = "stop_hook_active"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
REPLY_PARAGRAPH_SEPARATOR = "\n\n"

REPORT_TEMPLATE = (
    "{label} [{policy}]: replies {reply_count}, holds {hold_count}, footer copies {footer_count},"
    " repeated lines {repeated_line_count}"
)
HOLD_ROW_TEMPLATE = "  turn {turn_number} hold: {lead}"
TOP_LINE_ROW_TEMPLATE = "  x{count} {line}"
LINE_REPORT_TEMPLATE = (
    "replies {reply_count}, counted lines {line_count}, footer copies {footer_count},"
    " repeated lines {repeated_line_count}"
)
HOLD_LEAD_LENGTH = 90
SHOWN_LINE_LENGTH = 100

FOOTER_HEADING_LINE = "In progress:"
FOOTER_LIST_MARKER = "- "
UUID_KEY = "uuid"
UUID_TEMPLATE = "record-{number:04d}"
TOOL_NAME_KEY = "name"
TOOL_ID_KEY = "id"
TOOL_INPUT_KEY = "input"
TOOL_USE_ID_KEY = "tool_use_id"
