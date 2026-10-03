# Spawn routing

This family holds a helper spawn until the agent has gathered context, adjusts thread requests when usage exceeds pace, and selects an allowed subagent model.

## Checks

- `routing/spawn_readiness_hook.py` denies an agent spawn until the session records a read step and an answered question or a settled-scope line.
- `routing/thread_spawn_pace_hook.py` reshapes a thread request when usage is over pace or unreadable.
- `routing/subagent_model_routing.mjs` allows a selected Luna model, remaps eligible requests, and denies unsupported model routing.

## When it fires

- `routing/spawn_readiness_hook.py` runs on `PreToolUse` matcher `Agent|Task` at `10` seconds and matcher `mcp__hearthbot__start_thread_session` at `10` seconds in `hooks.json`.
- `routing/thread_spawn_pace_hook.py` runs on `PreToolUse`, matcher `mcp__hearthbot__start_thread_session`, timeout `30` seconds in `hooks.json`.
- `routing/subagent_model_routing.mjs` runs on `PreToolUse`, matcher `multi_agent_v1__spawn_agent`, timeout `10` seconds through the quoted Node command in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root. Python and pytest cover the two Python scripts; Node covers the model router.

- **Spawn readiness.** Input is a spawn after a read, a question, and its answer. Run `python -m pytest packages/claude-dev-env/hooks/routing/test_spawn_readiness_hook.py -q`. The adjacent test observes an allowed spawn and denials for missing steps.
- **Thread pace.** Input is a thread spawn with usage over pace. Run `python -m pytest packages/claude-dev-env/hooks/routing/test_thread_spawn_pace_hook.py -q`. The adjacent test observes updated tool input with the selected model, effort, and advisor line.
- **Model routing.** Input is a `multi_agent_v1__spawn_agent` payload with a model choice. Run `node --test packages/claude-dev-env/hooks/routing/subagent_model_routing.test.mjs`. The adjacent test observes an allow or deny decision with the routed model.

## Gotchas

- `routing/spawn_readiness_hook.py` also runs after the pace hook on thread spawns. A reshaped request still needs readiness.
- The readiness hook passes subagent calls, read-only helper types, and unreadable transcripts.
- The model router allows an advisor flag to bypass the Luna restriction. Its ordinary path denies unresolved or unsupported models.
