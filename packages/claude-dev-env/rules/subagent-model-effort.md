---
paths:
  - "**/agents/**"
  - "**/skills/**"
  - "**/hooks/**"
  - "**/workflows/**"
  - "**/docs/agent-spawn-protocol.md"
---

# Subagent model and effort

**When:** Write or change anything that starts another agent, such as an agent definition, a skill, a hook, a workflow or a `claude -p` command.

Name both the model and the effort on every spawn. The efforts each model may run at, and the effort it gets otherwise, are in [`subagent_effort_levels.json`](../hooks/hooks_constants/subagent_effort_levels.json). Use Anthropic models only. An advisor that is not the built-in advisor tool runs on Opus at high.

**Enforcement:** `hooks/routing/subagent_effort_route_hook.py` sets the allowed effort on Agent and Task spawns, and `hooks/routing/thread_spawn_pace_hook.py` does it for thread spawns that name a model.

**Full text:** [guide](../docs/rule-guides/subagent-model-effort.md). Read it when choosing which model gets which work. The [model choice guides](../docs/model-choice/README.md) cover escalation, caching, fan-out and measuring.
