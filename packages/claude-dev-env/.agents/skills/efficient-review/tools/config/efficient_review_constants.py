"""Paths and runtime markers for the efficient-review plan."""

from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
GATE_CONSTANTS_FILENAME = "haiku_spawn_slim_gate_constants.py"
GATE_MODULE_NAME = "haiku_spawn_slim_gate_constants"
HOOKS_DIRECTORY_NAME = "hooks"
HOOKS_CONSTANTS_DIRECTORY_NAME = "hooks_constants"
ALL_HOOKS_PARENT_STEPS = (1, 2)
USER_HOME_PARENT_STEP = 2
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
ALL_CLAUDE_HOST_VARIABLES = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
ALL_OTHER_HOST_VARIABLES = (
    "CURSOR_AGENT",
    "CURSOR_TRACE_ID",
    "CODEX_HOME",
    "CODEX_CI",
)
RUNTIME_CLAUDE = "claude"
RUNTIME_OTHER = "other"
MODEL_DEFERRED = "deferred"
PROFILE_DEFERRED = "deferred"
JSON_INDENT = 2
PLAN_COMMAND = "plan"
TEXT_ENCODING = "utf-8"
