"""Constants for the spawn oversight PreToolUse hook.

Groups: the spawn tools it answers, the workflow dispatch that carries an
agent prompt, the payload keys it reads, and the
oversight directive it adds to every spawn.
"""

from __future__ import annotations

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
ADDITIONAL_CONTEXT_KEY = "additionalContext"

WORKFLOW_DISPATCH_TOOL_NAME = "mcp__github__actions_run_trigger"
DISPATCH_METHOD_INPUT_KEY = "method"
DISPATCH_RUN_WORKFLOW_METHOD = "run_workflow"
DISPATCH_INPUTS_KEY = "inputs"
DISPATCH_PROMPT_INPUT_KEY = "prompt"

ALL_SPAWN_TOOL_NAMES = frozenset(
    {
        "Agent",
        "Task",
        "Workflow",
        "multi_agent_v1__spawn_agent",
        "mcp__hearthbot__start_thread_session",
        "mcp__hearthbot__start_rc_session",
    }
)

SPAWN_OVERSIGHT_DIRECTIVE = (
    "You own the work this spawn starts. Load the orchestrator skill and follow "
    "its Oversee delegated work section. While the agent runs, read its progress "
    "and wake it with one next step when it goes quiet. Before its output "
    "reaches the user, check it against the user's own words and standards, and "
    "send the agent a correction when it misses. Give each piece of a "
    "multi-piece task its own reviewer or helper. Tell the user you are "
    "checking the work."
)
