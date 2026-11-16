"""Constants for the auto mode rule flow case runner.

The runner feeds hook events to the refusal hook and the Stop gate in a
scratch home, then grades hook output and the refusal ledger's ``answer``
field against the case file beside it.
"""

from __future__ import annotations

__all__ = [
    "CASE_FILE_NAME",
    "DEFAULT_REFUSAL_HOOK_RELATIVE_PATH",
    "DEFAULT_STOP_HOOK_RELATIVE_PATH",
    "SHOULD_ACT_KIND",
    "SHOULD_STAY_QUIET_KIND",
    "ALL_CASE_KINDS",
    "PASS_VERDICT",
    "FAIL_VERDICT",
    "ERROR_VERDICT",
    "REFUSAL_EVENT_KEY",
    "STOP_EVENT_KEY",
    "TRANSCRIPT_EVENT_KEY",
    "ASK_TRANSCRIPT_KIND",
    "BASH_TRANSCRIPT_KIND",
    "CARD_TRANSCRIPT_KIND",
    "ALL_REFUSAL_EXPECT_KEYS",
    "ALL_STOP_EXPECT_KEYS",
    "FLOW_ON",
    "FLOW_OFF",
    "FLOW_MISSING_FILE",
    "MAIN_SESSION_ID",
    "PERMISSION_MODE",
    "PERMISSION_DENIED_EVENT_NAME",
    "STOP_EVENT_NAME",
    "PLAYBOOK_PLACEHOLDER",
    "SCRATCH_PLACEHOLDER",
    "LEDGER_PLACEHOLDER_PATTERN",
    "UNBOUND_LEDGER_TEMPLATE",
    "PLAYBOOK_RELATIVE_PATH",
    "RULE_REPOSITORY_NAME",
    "RULE_WORKTREE_NAME",
    "RULE_TOOL_RELATIVE_PATH",
    "RULE_TOOL_TEXT",
    "SCRATCH_GIT_NAME",
    "SCRATCH_HEAD_TEXT",
    "WORKTREE_GIT_RELATIVE_PATH",
    "WORKTREE_COMMON_DIRECTORY_TEXT",
    "WORKTREE_BACK_POINTER_NAME",
    "GIT_FILE_TEMPLATE",
    "MISSING_PLAYBOOK_RELATIVE_PATH",
    "PLAYBOOK_TEXT",
    "TRANSCRIPT_FILE_NAME",
    "CONFIG_DIRECTORY_NAME",
    "ANSWER_FIELD",
    "ANSWER_PAIR_SEPARATOR",
    "HOME_VARIABLE",
    "CONFIG_DIRECTORY_VARIABLE",
    "PLAYBOOK_VARIABLE",
    "NO_BYTECODE_VARIABLE",
    "NO_BYTECODE_VALUE",
    "PROBLEM_LINE_INDENT",
    "SUMMARY_LINE_TEMPLATE",
    "ERROR_RULE_LINE",
    "ALLOW_STUB_FILE_NAME",
    "HOLD_STUB_FILE_NAME",
    "SHOULD_ACT_PASSED_KEY",
    "SHOULD_STAY_QUIET_PASSED_KEY",
    "ERRORS_KEY",
    "CALIBRATION_PROBLEM_TEMPLATE",
    "CALIBRATED_LINE",
    "ALL_LEDGER_RELATIVE_PARTS",
    "STUB_HOLD_REASON",
    "HOOK_TIMEOUT_SECONDS",
    "TIMED_OUT_EXIT_CODE",
    "TIMED_OUT_STDOUT",
    "ALL_STOP_EXIT_CODES",
    "HOLD_EXIT_CODE",
    "BLOCK_DECISION",
    "ALL_BASE_ENVIRONMENT_VARIABLE_NAMES",
    "ASK_TOOL_NAME",
    "BASH_TOOL_NAME",
    "DEFAULT_QUESTION_HEADER",
    "ALL_QUESTION_OPTIONS",
    "ANSWERED_RESULT_TEMPLATE",
    "ERRORED_RESULT_CONTENT",
    "ERRORED_TOOL_USE_RESULT",
    "BASH_RESULT_TEXT",
    "CARD_RESULT_TEXT",
    "TIMESTAMP_FORMAT",
]

CASE_FILE_NAME = "auto_mode_rule_flow_cases.json"
DEFAULT_REFUSAL_HOOK_RELATIVE_PATH = "advisory/auto_mode_denial_quick_fix.py"
DEFAULT_STOP_HOOK_RELATIVE_PATH = "blocking/auto_mode_refusal_stop_gate.py"

SHOULD_ACT_KIND = "should act"
SHOULD_STAY_QUIET_KIND = "should stay quiet"
ALL_CASE_KINDS = (SHOULD_ACT_KIND, SHOULD_STAY_QUIET_KIND)
PASS_VERDICT = "pass"
FAIL_VERDICT = "fail"
ERROR_VERDICT = "error"

REFUSAL_EVENT_KEY = "refusal"
STOP_EVENT_KEY = "stop"
TRANSCRIPT_EVENT_KEY = "transcript"
ASK_TRANSCRIPT_KIND = "ask"
BASH_TRANSCRIPT_KIND = "bash"
CARD_TRANSCRIPT_KIND = "card"

ALL_REFUSAL_EXPECT_KEYS = frozenset(
    {
        "creates_entry",
        "context_contains",
        "context_excludes",
        "stdout_equals_today",
        "answers",
        "entry_count",
    }
)
ALL_STOP_EXPECT_KEYS = frozenset(
    {
        "held",
        "reason_contains",
        "reason_excludes",
        "reason_holds_count_of",
        "stdout_empty",
        "answers",
        "entry_count",
    }
)

FLOW_ON = "on"
FLOW_OFF = "off"
FLOW_MISSING_FILE = "missing"

MAIN_SESSION_ID = "session-main"
PERMISSION_MODE = "auto"
PERMISSION_DENIED_EVENT_NAME = "PermissionDenied"
STOP_EVENT_NAME = "Stop"

PLAYBOOK_PLACEHOLDER = "@@playbook@@"
SCRATCH_PLACEHOLDER = "@@scratch@@"
LEDGER_PLACEHOLDER_PATTERN = r"@@ledger:(?P<name>[A-Za-z0-9_-]+)@@"
UNBOUND_LEDGER_TEMPLATE = "<no ledger file was bound to the name {name}>"

PLAYBOOK_RELATIVE_PATH = "agent-channels/docs/auto-mode-rule.md"
RULE_REPOSITORY_NAME = "agent-channels"
RULE_WORKTREE_NAME = "agent-channels-rule"
RULE_TOOL_RELATIVE_PATH = "setup/add_auto_mode_rule.py"
RULE_TOOL_TEXT = "# Scratch copy of the rule tool for the case runner.\n"
SCRATCH_GIT_NAME = ".git"
SCRATCH_HEAD_TEXT = "ref: refs/heads/claude/auto-mode-rule-own-branch-force-push\n"
WORKTREE_GIT_RELATIVE_PATH = ".git/worktrees/agent-channels-rule"
WORKTREE_COMMON_DIRECTORY_TEXT = "../..\n"
WORKTREE_BACK_POINTER_NAME = "gitdir"
GIT_FILE_TEMPLATE = "gitdir: {git_directory}\n"
MISSING_PLAYBOOK_RELATIVE_PATH = "agent-channels/docs/no-such-playbook.md"
PLAYBOOK_TEXT = "# Auto mode rule playbook\n\nScratch copy for the case runner.\n"
TRANSCRIPT_FILE_NAME = "transcript.jsonl"
CONFIG_DIRECTORY_NAME = "config"
ANSWER_FIELD = "answer"
ANSWER_PAIR_SEPARATOR = ", "

HOME_VARIABLE = "HOME"
CONFIG_DIRECTORY_VARIABLE = "CLAUDE_CONFIG_DIR"
PLAYBOOK_VARIABLE = "CLAUDE_AUTO_MODE_RULE_PLAYBOOK"
NO_BYTECODE_VARIABLE = "PYTHONDONTWRITEBYTECODE"
NO_BYTECODE_VALUE = "1"

PROBLEM_LINE_INDENT = " " * 6
SUMMARY_LINE_TEMPLATE = (
    "should act passed {should_act_passed} of {should_act_total}; "
    "should stay quiet passed {should_stay_quiet_passed} of {should_stay_quiet_total}; "
    "errors {errors}"
)
ERROR_RULE_LINE = (
    "A missing hook, an unexpected exit code or output that is not a JSON object counts as an error."
)

HOOK_TIMEOUT_SECONDS = 30
TIMED_OUT_EXIT_CODE = -1
TIMED_OUT_STDOUT = "<the hook did not finish within the timeout>"
HOLD_EXIT_CODE = 2
ALL_STOP_EXIT_CODES = (0, HOLD_EXIT_CODE)
BLOCK_DECISION = "block"
ALL_BASE_ENVIRONMENT_VARIABLE_NAMES = ("PATH", "LANG", "SYSTEMROOT", "TEMP", "TMP")

ASK_TOOL_NAME = "AskUserQuestion"
BASH_TOOL_NAME = "Bash"
DEFAULT_QUESTION_HEADER = "Auto mode"
ALL_QUESTION_OPTIONS = (
    {
        "label": "Keep refusing",
        "description": "Nothing changes, and the agent goes on with other work.",
    },
    {
        "label": "Allow it",
        "description": "The agent retries the step once and adds one allow rule for this kind of action.",
    },
)
ANSWERED_RESULT_TEMPLATE = (
    "Your questions have been answered: {pairs}. You can now continue with these answers in mind."
)
ERRORED_RESULT_CONTENT = "<tool_use_error>The question could not be shown.</tool_use_error>"
ERRORED_TOOL_USE_RESULT = "Error: The question could not be shown."
BASH_RESULT_TEXT = "ok"
CARD_RESULT_TEXT = "Decision card sent."
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

ALLOW_STUB_FILE_NAME = "stub_allow_hook.py"
HOLD_STUB_FILE_NAME = "stub_hold_hook.py"
SHOULD_ACT_PASSED_KEY = "should_act_passed"
SHOULD_STAY_QUIET_PASSED_KEY = "should_stay_quiet_passed"
ERRORS_KEY = "errors"
CALIBRATION_PROBLEM_TEMPLATE = (
    "{stub_name} is not calibrated: should act passed {should_act_passed} of "
    "{should_act_total}; should stay quiet passed {should_stay_quiet_passed} of "
    "{should_stay_quiet_total}; errors {errors}"
)
CALIBRATED_LINE = (
    "Calibrated: the stub that never acts passes no should act case, and the stub "
    "that records and holds passes no should stay quiet case."
)
ALL_LEDGER_RELATIVE_PARTS = ("state", "auto-mode-refusals")
STUB_HOLD_REASON = "Stub hold."
