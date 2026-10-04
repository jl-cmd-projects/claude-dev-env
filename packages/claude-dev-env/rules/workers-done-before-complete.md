---
paths:
  - "**/skills/orchestrator/**"
  - "**/skills/orchestrator-refresh/**"
---

# Workers done before complete

**When:** Mark a task `completed` after spawning subagents, workflow agents, or background shells.

List every worker and confirm that each has finished and its result is merged into run state. Verify worker file lists, counts, descriptions, and findings against the repository and diff before repeating them. While a worker runs or output is missing, keep the task `in_progress`, report dead or hung workers, schedule a wakeup, and keep other work moving. Check the task goal against merged state before closing.

**Enforcement:** none, the agent applies it.

**Full text:** [`docs/rule-guides/workers-done-before-complete.md`](../docs/rule-guides/workers-done-before-complete.md). Read it before closing a task that spawned workers.
