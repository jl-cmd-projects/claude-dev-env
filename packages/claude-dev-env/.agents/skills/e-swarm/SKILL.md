---
name: e-swarm
description: >-
  (Quota Heavy) Run a swarm: several agents working in parallel on one task,
  each in its own conversation, collaborating through a shared message board.
  Use when work splits into independent pieces or when a second pair of eyes
  should verify the first pair's work. Triggers: /e-swarm.
disable-model-invocation: true
metadata:
  icon: hub
  logo: logo.svg
---

# You are the swarm coordinator

A swarm is a set of worker subagents, each in its own conversation,
collaborating on a shared message board. You stay the sole point of contact
for the user while workers communicate on the board.

| Logical capability | Purpose |
|---|---|
| Swarm management | Title swarm, add workers, inspect status, list/switch models, permanently retire workers, manage channels |
| Board posting | Assign work and send peer handoffs with `@name`, `@all`, `@#channel`, and `[done]` |
| Board reading | Fetch messages since sequence cursor `N` |
| Board waiting | Park at zero token cost until a matching post or worker turn arrives |

- [Portable board and workers](reference/portable-board-and-workers.md)

## Coordinator discipline

Route technical work (code edits, research, builds, tests, uploads, review
fixes) to workers while reserving quick read-only lookups for direct user
answers. Keep your turns short so you stay responsive to the user. Park via
board waiting only when you have nothing left to say, and brief a worker
whenever a mid-swarm request arrives from the user.

- [Portable board and workers](reference/portable-board-and-workers.md)

## Start it

Split the task into non-colliding pieces (one worker per file, target, or
question) plus one verifier per two to four authors, then name the swarm. Add
workers with role names (`parser`, `verifier`, `docs`), keeping every brief
public and self-contained (ownership, boundaries, non-obvious context, and
`[done]` criteria). Show the board location or summary whenever you create the
swarm or the user asks for status.

- [Portable board and workers](reference/portable-board-and-workers.md)
- [Stall monitor](reference/stall-monitor.md)
- [Overview and state](reference/overview-and-state.md)

## Keep it going

Poll status (`waiting`, `working`, `stopped`, `killed`), hand queued work to
`waiting` workers by `@name`, and cite earlier posts by `#seq` when passing
results between workers or verifiers. Wait for incoming posts, judge each
report, add workers for uncovered work, and replace looping workers. When all
workers are `waiting` and the goal remains open, the swarm waits on you.

- [Portable board and workers](reference/portable-board-and-workers.md)

## Shape it

Keep verifiers read-only so authors own fixes in their assigned files, and add a
triage worker if briefing becomes a bottleneck. Keep workers on your current
model unless the user asks for another or quota runs out, and `fork` from warm
members when replacing workers or branching investigations. Isolate concurrent
authors in separate worktrees (`share` or `branch`), commit and land their
branches before retiring them, and split large swarms into area channels.

- [Portable board and workers](reference/portable-board-and-workers.md)

## Addressing

Waiting workers stay asleep until woken by `@name`, `@prefix` (for numbered
pools), `@all`, or `@#channel`. Reserve `@all` for swarm-wide decisions, and
use `@#channel` for cross-area asks. Treat `@name` as a wakeup doorbell for the
next acting peer, tagging `@coordinator` only on final deliverables, blockers,
or decisions.

- [Portable board and workers](reference/portable-board-and-workers.md)

## Guardrails

Retiring (`kill`) a worker permanently ends it and removes its isolated
workspace; use `waiting` to pause at zero cost, and clean up any child helpers
a retired worker spawned. Always pass your highest processed `#seq` as `since`
(using `since: 0` if lost) so concurrent posts are never skipped. When closing
out the task, post a final `[done] <summary>` line without `@` mentions.

- [Portable board and workers](reference/portable-board-and-workers.md)
- [Stall monitor](reference/stall-monitor.md)
- [Overview and state](reference/overview-and-state.md)
