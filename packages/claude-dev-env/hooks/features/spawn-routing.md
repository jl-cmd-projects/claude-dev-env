# Spawn routing

This family reminds the agent to gather context before a spawn, tells it that it owns the spawned work, adjusts thread requests when usage exceeds pace, selects an allowed subagent model, and sends a Haiku spawn to a headless slim-profile run.

## Checks

- `routing/spawn_readiness_hook.py` adds context to a spawn that comes before a read step, or before an answered question or a settled-scope line. The spawn still runs.
- `routing/spawn_oversight_hook.py` adds the orchestrator oversight directive to every spawn: watch the agent, check its output against the user's words and standards, and correct it before the output reaches the user. The spawn still runs.
- `routing/thread_spawn_pace_hook.py` reshapes a thread request when usage is over pace or unreadable.
- `routing/subagent_model_routing.mjs` allows a selected Luna model, remaps eligible requests, and denies unsupported model routing.
- `blocking/haiku_spawn_slim_gate.py` denies an Agent, Task, or thread spawn whose `model` names Haiku. The deny reason gives the headless `claude -p` command that loads the slim profile through the account broker.

## When it fires

- `routing/spawn_readiness_hook.py` runs on `PreToolUse` with matchers `Agent|Task`, `multi_agent_v1__spawn_agent`, `Workflow|mcp__github__actions_run_trigger`, and `mcp__hearthbot__start_thread_session`, each at `10` seconds in `hooks.json`. A workflow dispatch counts only when its inputs carry a `prompt`.
- `routing/spawn_oversight_hook.py` runs on `PreToolUse` with matchers `Agent|Task`, `multi_agent_v1__spawn_agent`, `Workflow|mcp__github__actions_run_trigger`, `mcp__hearthbot__start_thread_session`, and `mcp__hearthbot__start_rc_session`, each at `10` seconds in `hooks.json`. A workflow dispatch counts only when its inputs carry a `prompt`.
- `routing/thread_spawn_pace_hook.py` runs on `PreToolUse`, matcher `mcp__hearthbot__start_thread_session`, timeout `30` seconds in `hooks.json`.
- `routing/subagent_model_routing.mjs` runs on `PreToolUse`, matcher `multi_agent_v1__spawn_agent`, timeout `10` seconds through the quoted Node command in `hooks.json`.
- `blocking/haiku_spawn_slim_gate.py` runs on `PreToolUse` with matchers `Agent|Task` and `mcp__hearthbot__start_thread_session`, each at `10` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root. Python and pytest cover the two Python scripts; Node covers the model router.

- **Spawn readiness.** Input is a spawn after a read, a question, and its answer. Run `python -m pytest packages/claude-dev-env/hooks/routing/test_spawn_readiness_hook.py -q`. The adjacent test observes no output for a ready spawn and reminder context for each missing step.
- **Spawn oversight.** Input is a spawn from each registered tool, a subagent's own spawn, and a non-spawn call. Run `python -m pytest packages/claude-dev-env/hooks/routing/test_spawn_oversight_hook.py -q`. The adjacent test observes the directive for every spawn and no output for the other calls.
- **Thread pace.** Input is a thread spawn with usage over pace. Run `python -m pytest packages/claude-dev-env/hooks/routing/test_thread_spawn_pace_hook.py -q`. The adjacent test observes updated tool input with the selected model, effort, and advisor line.
- **Haiku slim gate.** Input is a spawn with a Haiku alias or model ID, and spawns on other models or with no model. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_haiku_spawn_slim_gate.py -q`. The adjacent test observes a deny with the headless command for each Haiku spawn and no output for the rest.
- **Model routing.** Input is a `multi_agent_v1__spawn_agent` payload with a model choice. Run `node --test packages/claude-dev-env/hooks/routing/subagent_model_routing.test.mjs`. The adjacent test observes an allow or deny decision with the routed model.

## Gotchas

- `routing/spawn_readiness_hook.py` also runs after the pace hook on thread spawns. A reshaped request still gets the readiness check.
- The oversight hook fires inside subagents too, so each level of the tree oversees the level below it. It emits `additionalContext` only and never blocks.
- The readiness hook emits `additionalContext` only, so it never blocks. It passes subagent calls, read-only helper types, a non-object tool input, and unreadable transcripts.
- The Haiku slim gate reads only the spawn's `model` field. A spawn that names no model passes, even when its agent definition or `CLAUDE_CODE_SUBAGENT_MODEL` resolves it to Haiku.
- The model router allows an advisor flag to bypass the Luna restriction. Its ordinary path denies unresolved or unsupported models.
