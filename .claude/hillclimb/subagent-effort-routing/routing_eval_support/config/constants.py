"""Configuration for the subagent-effort-routing session eval."""

from pathlib import Path

FLOW_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FLOW_ROOT.parents[2]
SHARED_FLOW_ROOT = FLOW_ROOT.parent / "features-start-with-an-eval"
CASES_FILE = FLOW_ROOT / "cases.json"
STATE_FILE = FLOW_ROOT / "_state.json"
CLAUDE_PROJECTS_DIRECTORY = Path.home() / ".claude" / "projects"
CHILD_TRANSCRIPT_PATTERN_TEMPLATE = "*/{session_id}/subagents/agent-*.jsonl"
CHILD_META_SUFFIX = ".meta.json"
CHILD_TRANSCRIPT_SUFFIX = ".jsonl"
WORKSPACE_SETTINGS_TARGET = ".claude/settings.json"
HOOK_COMMAND_TEMPLATE = "python3 {hook_path}"
HOOK_TIMEOUT_SECONDS = 10
HOOK_EVENT_NAME = "PreToolUse"
COMMAND_HOOK_TYPE = "command"

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "high"
DEFAULT_MAX_TURNS = 8
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_REPS = 2
DEFAULT_PARALLEL = 4
ALLOWED_TOOLS = "Agent,Task,Read,Grep,Glob"
ALL_EXTRA_SESSION_WORDS = ("--allowedTools", ALLOWED_TOOLS, "--include-hook-events")

ALL_SPAWN_TOOL_NAMES = frozenset({"Agent", "Task"})
FORK_SUBAGENT_TYPE = "fork"
MODEL_INPUT_KEY = "model"
EFFORT_INPUT_KEY = "effort"
SUBAGENT_TYPE_INPUT_KEY = "subagent_type"

ALL_ALLOWED_EFFORTS_BY_FAMILY: dict[str, frozenset[str]] = {
    "opus": frozenset({"medium"}),
    "sonnet": frozenset({"high"}),
    "fable": frozenset({"low", "medium", "high"}),
    "haiku": frozenset({"low", "medium", "high", "xhigh", "max"}),
}

HOOK_RESPONSE_SUBTYPE = "hook_response"
SESSION_ID_FIELD = "session_id"
HOOK_OUTPUT_FIELD = "output"
HOOK_SPECIFIC_OUTPUT_FIELD = "hookSpecificOutput"
UPDATED_INPUT_FIELD = "updatedInput"
ASSISTANT_ENTRY_TYPE = "assistant"
ENTRY_TYPE_FIELD = "type"
ENTRY_MESSAGE_FIELD = "message"
ENTRY_EFFORT_FIELD = "effort"
ENTRY_TURN_EFFORT_FIELD = "perTurnEffort"
META_TOOL_USE_ID_FIELD = "toolUseId"
META_AGENT_TYPE_FIELD = "agentType"

FAILURE_NO_CHILD_TRANSCRIPT = "no-child-transcript"
ALL_RATE_METRIC_IDS = ("in_rule", "named_in_rule", "routed")
SPAWNED_METRIC_ID = "spawned"
ALL_HOOK_SOURCE_PATHS = (
    "packages/claude-dev-env/hooks/routing/subagent_effort_route.py",
    "packages/claude-dev-env/hooks/hooks_constants/subagent_effort_route_constants.py",
)
JSON_INDENT = 2
SUMMARY_SEPARATOR = " | "
