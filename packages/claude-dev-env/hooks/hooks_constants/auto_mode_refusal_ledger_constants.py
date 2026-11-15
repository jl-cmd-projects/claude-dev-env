"""Constants for the auto mode refusal ledger.

The ledger keeps one file per refused step and one question record per
question text under ``<config>/state/auto-mode-refusals/<session_id>/``.
The refusal hook and the Stop gate both read and write it.
"""

from __future__ import annotations

__all__ = [
    "PLAYBOOK_ENVIRONMENT_VARIABLE",
    "ALL_LEDGER_RELATIVE_PARTS",
    "ENTRY_FILE_SUFFIX",
    "QUESTION_FILE_PREFIX",
    "QUESTION_RECORD_KIND",
    "ID_HEX_CHARACTERS",
    "TEMPORARY_FILE_PREFIX",
    "TEMPORARY_FILE_SUFFIX",
    "TEXT_ENCODING",
    "JSON_INDENT_SPACES",
    "ALLOWED_ANSWER",
    "KEPT_ANSWER",
    "ALL_ANSWERS",
    "ANSWER_BY_OPTION_LABEL",
    "ASK_TOOL_NAME",
    "MAXIMUM_STEPS_PER_QUESTION",
    "SINGLE_STEP_QUESTION_TEMPLATE",
    "SEVERAL_STEPS_QUESTION_TEMPLATE",
    "PLAYBOOK_ROOT_DEPTH",
    "ALL_RULE_ROOT_MARKER_PATHS",
    "TIMESTAMP_FORMAT",
]

PLAYBOOK_ENVIRONMENT_VARIABLE = "CLAUDE_AUTO_MODE_RULE_PLAYBOOK"
ALL_LEDGER_RELATIVE_PARTS = ("state", "auto-mode-refusals")
ENTRY_FILE_SUFFIX = ".json"
QUESTION_FILE_PREFIX = "question-"
QUESTION_RECORD_KIND = "question"
ID_HEX_CHARACTERS = 16
TEMPORARY_FILE_PREFIX = ".auto-mode-refusal-"
TEMPORARY_FILE_SUFFIX = ".tmp"
TEXT_ENCODING = "utf-8"
JSON_INDENT_SPACES = 2

ALLOWED_ANSWER = "allowed"
KEPT_ANSWER = "kept"
ALL_ANSWERS = frozenset({ALLOWED_ANSWER, KEPT_ANSWER})
ANSWER_BY_OPTION_LABEL = {
    "Allow it": ALLOWED_ANSWER,
    "Allow it (Recommended)": ALLOWED_ANSWER,
    "Keep refusing": KEPT_ANSWER,
    "Keep refusing (Recommended)": KEPT_ANSWER,
}
ASK_TOOL_NAME = "AskUserQuestion"

MAXIMUM_STEPS_PER_QUESTION = 5
SINGLE_STEP_QUESTION_TEMPLATE = (
    "Auto mode refused 1 {tool_name} step under the {rule_label} rule. "
    "Should auto mode have refused it?"
)
SEVERAL_STEPS_QUESTION_TEMPLATE = (
    "Auto mode refused {step_count} {tool_name} steps under the {rule_label} rule. "
    "Should auto mode have refused them?"
)

PLAYBOOK_ROOT_DEPTH = 2
ALL_RULE_ROOT_MARKER_PATHS = (".git", "setup/add_auto_mode_rule.py")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
