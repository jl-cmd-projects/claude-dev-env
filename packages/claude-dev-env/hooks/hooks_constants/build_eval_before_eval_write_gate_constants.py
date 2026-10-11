"""Constants for the gate that holds eval file writes until /claude-api build-eval runs."""

ALL_FILE_WRITE_TOOL_NAMES = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
ALL_FILE_PATH_FIELDS = ("file_path", "notebook_path")
ALL_EVAL_DIRECTORY_NAMES = frozenset({"eval", "evals", "hillclimb"})
EVAL_FILE_NAME_WORD_PATTERN = r"(?:^|[._-])evals?(?:[._-]|$)"
PATH_SEPARATOR_PATTERN = r"[\\/]"
MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON = (
    "This file is part of an eval, and this session has not invoked /claude-api"
    " build-eval. An eval starts with that skill. Invoke the Skill tool with skill"
    " 'claude-api' and args 'build-eval', follow the guide it loads, then write this"
    " file again. Read docs/rule-guides/features-start-with-an-eval.md for the rule."
)
