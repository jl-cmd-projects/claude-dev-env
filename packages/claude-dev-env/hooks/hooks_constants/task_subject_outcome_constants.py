"""Constants for task_subject_outcome_gate.py."""

import re

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
GATE_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2

TASK_CREATE_TOOL_NAME = "TaskCreate"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"
TODO_WRITE_TOOL_NAME = "TodoWrite"
ALL_SUBJECT_TOOL_NAMES = frozenset({TASK_CREATE_TOOL_NAME, TASK_UPDATE_TOOL_NAME})
TASK_SUBJECT_KEY = "subject"
TODOS_KEY = "todos"
TODO_CONTENT_KEY = "content"

PROCEDURE_STEP_PREFIX_PATTERN = re.compile(
    r"^\s*(?:step|phase|stage|part|feature|bug\s+fix|refactoring|playbook)"
    r"\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s*(?:[:)]|\.(?!\d))",
    re.IGNORECASE,
)
CODE_SPAN_MARKER = "`"

PROCEDURE_STEP_MESSAGE = (
    "The task subject '{subject}' starts with a procedure step label such as 'Step 3:' or"
    " 'Feature 6-8:'."
)
CODE_SPAN_MESSAGE = "The task subject '{subject}' holds a code-formatted name in backticks."
RETRY_INSTRUCTION = (
    " The user follows the task list to see where the work stands and what is left."
    " Name the item by its outcome in the user's words, such as"
    " 'Task names in the list read as outcomes'."
    " Keep playbook steps, skill names, and other procedure steps in a private checklist"
    " file such as todo.md in the work folder, and call the tool again."
)
