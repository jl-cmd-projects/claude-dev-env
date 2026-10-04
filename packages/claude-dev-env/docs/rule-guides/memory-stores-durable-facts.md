# Memory Stores Durable Facts

Full text behind [`rules/memory-stores-durable-facts.md`](../../rules/memory-stores-durable-facts.md).

**When this applies:** Before you write or update a file in an auto-memory
directory, and before you add its line to `MEMORY.md`.

## Rule

A memory must still help a fresh session, with no context, weeks later.

Run one test on the draft. Strip every date, pull request number, issue number,
commit, job path, session ID, and task number. When what remains is empty or
false, the draft is run state. Put it in the task tracker, the pull request, or
a handoff file beside the work, and save no memory.

## What never becomes a memory

| Shape | Example | Where it belongs |
|---|---|---|
| Run or program state | "paused at", "resume from", "4 of 11 merged", a pointer to a handoff file | The task tracker or the handoff file |
| A pull request, issue, stack, or commit map | "#583, #605, #610 merged" | The epic issue or the pull request |
| A temporary condition | A concurrency schedule, credits out, a fleet that works this week, a fix "until X lands" | The current conversation |
| One session's topology | A session ID, a parallel session's worktree, a second-account dispatch setup | The current conversation |
| A workaround for a hook, gate, or verifier as it behaved one day | "the minter never fires, so skip the check" | A fix to the hook, per [`correction-lens.md`](../../rules/correction-lens.md) |
| The story of one incident or bug fix | "the fold checkbox took five tries" | Git history and the pull request body |
| Where code lives, or a design recipe for one build phase | A module layout, a prompt recipe for one engine version | The repository and its inventories |
| A restatement of a rule file | "CI owns the gate" | The rule file already loaded |

## What a memory holds

- A preference or standing order the user stated, with the date the user set it.
- A trap in the local setup or the platform that continues to apply, such as a shared
  `rr-cache` that replays one-sided resolutions without a marker.
- A pointer to an external resource: a dashboard, a repository, a tracker.

Write the fact first. A date belongs only on a rule the user set on that date.

## Keeping the folder current

When a memory goes stale, delete it and its `MEMORY.md` line in the same run.
A "superseded" note on a stale memory keeps a false fact loading into every
session.

## Why

One project's memory folder held 104 index entries. A cleanup pass removed 57
of them, and each one failed the test above. Handoffs outlived their work,
pull request maps named merged branches, and a capacity schedule and a
dispatch topology contradicted newer standing orders. Every stale memory loads
into each session and reads as current.

## Sibling rules

| Rule | Role |
|---|---|
| [`correction-lens.md`](../../rules/correction-lens.md) | A memory records a decision, and the control holds the behavior |
| [`verify-before-asking.md`](../../rules/verify-before-asking.md) | A recalled fact is a claim to re-check |
| [`cleanup-temp-files.md`](../../rules/cleanup-temp-files.md) | Scratch output leaves with the task |
