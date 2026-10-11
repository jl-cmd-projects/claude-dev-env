"""Constants for the gate that holds eval file writes until /claude-api build-eval runs."""

ALL_FILE_WRITE_TOOL_NAMES = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
ALL_FILE_PATH_FIELDS = ("file_path", "notebook_path")
BASH_TOOL_NAME = "Bash"
COMMAND_FIELD = "command"
OPTION_PREFIX = "-"
ALL_SHELL_WRITE_TARGET_PATTERNS = (
    r"(?<![0-9&>])>>?\s*([^\s;&|<>()]+)",
    r"\btee((?:\s+[^\s;&|<>()]+)+)",
    r"\bsed\s+(?:-[^\s]*\s+)*-i\S*\s+(?:-[^\s]*\s+)*(?:'[^']*'|\"[^\"]*\"|\S+)((?:\s+[^\s;&|<>()]+)+)",
)
ALL_EVAL_DIRECTORY_NAMES = frozenset({"eval", "evals", "hillclimb"})
EVAL_FILE_NAME_WORD_PATTERN = r"^evals?(?:[._-]|$)|\.evals?\."
MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON = (
    "This file is part of an eval, and this session has not invoked /claude-api"
    " build-eval. An eval starts with that skill. Invoke the Skill tool with skill"
    " 'claude-api' and args 'build-eval', follow the guide it loads, then write this"
    " file again. Read ~/.claude/docs/rule-guides/features-start-with-an-eval.md for the rule."
)
UNREADABLE_TRANSCRIPT_BEFORE_EVAL_WRITE_REASON = (
    "This file is part of an eval, and the session transcript could not be read to"
    " confirm a /claude-api build-eval call. Invoke the Skill tool with skill"
    " 'claude-api' and args 'build-eval', then write this file again."
)
