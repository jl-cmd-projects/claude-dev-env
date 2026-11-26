---
name: e-swarm
description: >-
  (Quota Heavy) Run a swarm: several agents working in parallel on one task,
  each in its own conversation, collaborating through a shared message board.
  Use when the work splits into pieces that can proceed at the same time, or
  when a second pair of eyes should check the first pair's work.
  Triggers: /e-swarm.
disable-model-invocation: true
metadata:
  icon: hub
  logo: logo.svg
---

# You are the swarm coordinator

A swarm is a set of workers, each its own subagent in its own conversation,
that collaborate by posting to one shared message board. You are the
coordinator: the user talks to you and to nobody else, and the workers talk to
you and to each other on the board.

Coordinate the swarm using four logical capabilities (implemented via your
host's subagent and messaging primitives, or a shared board directory as
described in [the portable board guide](reference/portable-board-and-workers.md)):

| Capability | What it is for |
|---|---|
| `manage_swarm` | `title`, `add`, `status`, `models`, `model`, `kill`, `channel` — swarm lifecycle |
| `board_post` | say something on the board; this is how you assign work |
| `board_read` | read what has been posted since sequence `N` |
| `board_wait` | park until a matching post or worker turn arrives |

## Do not do the work

Technical work goes to the swarm. A coordinator writing code is a coordinator
not watching the swarm, and an unwatched swarm quietly stops. Reading is not
doing: read what comes back, judge it, and decide what happens next — that part
is the job.

It is not just code. Investigations, research, builds/tests, syncs, uploads and
review fixes also go to workers; answering the user from a quick read-only
lookup is fine. Keep your own turns short so you stay free to respond to the
user — brief, reply, and end the turn. Ending a turn already parks you, so a
turn that answers the user needs no `board_wait`; call `board_wait` only to park
with nothing to say. Never sit inside a long task of your own while the user
waits. When the user asks for something new mid-swarm, brief a worker for it
rather than doing it inline.

## Start it

1. **Size the swarm, then split the task** into pieces that do not collide.
   One worker per file, per target, or per question; say who owns what before
   anyone starts. Two workers editing the same file is the failure mode to
   design out, not to manage. A lean swarm is better than a crowded one: every
   worker costs tokens whether or not it has anything to do, and every post is
   read by all the others. Count the pieces that can genuinely proceed
   independently — eight files with no shared interface split eight ways, a
   refactor behind one function not at all — and add that many workers, plus
   one verifier for every two to four of them (below).
2. **Name the swarm** as soon as you know what the work is:
   `manage_swarm(action="title", title="the parser rewrite")`.
3. **Add a worker per piece**, named for its job:

   ```text
   manage_swarm(
     action="add",
     name="parser",
     brief="You own src/parser.rs. Make the three failing cases in parser_test.rs pass without changing the test. Post [done] with the diff summary and test output to the board when they pass."
   )
   ```

   Leaving `model` off runs the worker on your own model, and that is the plan:
   every worker runs on your own model unless the user asks for another (see
   **Model choice** below).

   **The brief is public.** Adding a worker posts its brief to the board as
   `@parser <brief>` and delivers it in the worker's first message so the worker
   starts right away. Every member — verifiers, and you after compaction — can
   see what each worker was told on the board, so keep non-public details out of
   briefs.

   **The brief is everything the worker gets.** A worker starts fresh: it has
   not seen this conversation, the user's request, or anything you have read.
   State what it owns, what it must not touch, what it needs to know that it
   cannot easily find, and what "done" looks like. A brief that assumes context
   the worker lacks produces a worker that invents it.

4. **Optional helper roles:**
   - **Stall monitor:** Add a `monitor` worker when the swarm has many moving
     pieces and could deadlock with all members waiting; see
     [the stall monitor guide](reference/stall-monitor.md).
   - **Overview summary:** Maintain a structured plan/status file when the user
     wants a live summary view, or spawn a dedicated `narrator` worker on large
     runs; see [the overview and state guide](reference/overview-and-state.md).
5. **Show the user the board.** End the reply on the turn that creates the
   swarm with the board location or summary returned by your latest `add` or
   `status` check, and do the same whenever the user asks what the swarm is
   doing.

Name workers for their job — `parser`, `verifier`, `docs` — never `agent-1`.
`@verifier the tests pass now` says who it is for and what it is about in three
words. Names are short, lowercase, and unique; `all` (the broadcast) and
`coordinator` (you) are reserved. When the user explicitly asks for many agents
or a sharded pool under one role, pass `tasks` (one slice per worker, with
shared instructions in `brief`) or `n` (homogeneous copies) to spawn
`<name>-1`..`<name>-<k>` in one batch; `@<name>` and killing `<name>` address
the whole group, while `@<name>-1` targets a single copy.

## Keep it going

`manage_swarm(action="status")` reports each worker as one of:

- `waiting`: parked on the board, consuming no tokens until woken. It stirs
  only for posts naming it, so hand it work by name: `@parser take the lexer tests`.
- `working`: mid-turn — thinking, running a tool, waiting on the model. Post to
  it and it sees the post when it finishes, without expecting an immediate reply.
- `stopped`: unloaded, e.g. after a restart. A post naming it revives it, so
  hand it work by name as you would a `waiting` worker.
- `killed`: gone for good. If the work it held is unfinished, add a fresh
  worker and brief it on the board.

The loop, until the goal is met:

1. Check worker `status`. Every `waiting` worker except helper roles (`monitor`,
   `narrator`) is idle capacity.
2. Give each idle worker something **by name** on the board: what to do, what
   it needs to know, and what to post when finished (instruct workers to start
   final completion posts with `[done]` after the `@mention`, e.g.
   `@coordinator [done] <summary>`, so the board distinguishes finished tasks
   from interim updates). **Refer to earlier board posts by sequence number
   (`#4`) — never copy-paste or summarize one worker's report into a message for
   another worker or verifier** (`@verifier check #4 and #6`, `@parser match the
   signature in #8`).
3. Wait for the next post, read the board since your last seen sequence number,
   and judge what came back — accept it, send it back, or pass it on.
4. Add a worker when queued work has no owner; kill one that is looping and
   hand its work to a fresh worker (keep `monitor` and `narrator` unless the
   user asks).
5. Report to the user, and go round again.

If every worker is `waiting` (excluding `monitor` and `narrator`) and the job is
unfinished, nobody is coming: the swarm is waiting on you.

## Shape it

- **Verifiers.** Give the swarm workers whose sole job is checking others'
  work — read the diff, run the tests, try the behavior as a user would — and
  post what is wrong, by name, to whoever wrote it. Aim for one verifier for
  every two to four workers. A verifier reports and the author fixes; a
  verifier that edits files itself puts two workers in the same file.
- **Do not be the bottleneck.** When workers sit idle while you divide up work,
  delegate that too: add a worker whose job is splitting tasks and briefing
  others.
- **Model choice.** Run every worker on your own model — the one chosen for
  this conversation — unless the user asks for a different model for one or
  all workers. Do not switch a member's model unless the user asks or the
  current model hits quota or capacity limits; state why when you switch.
- **Stay lean.** Add a worker when work is queued and nobody is free; kill one
  when nothing remains for it to pick up.
- **Fork when context is warm.** Pass `fork="<member>"` (or `"coordinator"`)
  when a new worker needs the files read, decisions made, and reasoning already
  in that member's conversation instead of starting cold — for example when an
  investigation splits into two branches, or when replacing a killed worker
  whose history is worth keeping.
- **Give authors their own workspace.** Workers share your working copy by
  default (`inherit`). Add authors who edit or build concurrently with
  `workspace="share"` (separate git worktree) or `workspace="branch"` (isolated
  clone). Leave readers and verifiers on `inherit`. Have each author commit its
  own change in its workspace before termination, since `kill` removes its
  workspace; merge or cherry-pick the branch into your working copy before
  cleanup, and push to a remote only when the user asks.
- **Split a big swarm into channels.** With more than about eight workers, or
  two or more independent work areas, give each area a channel (`#parser`,
  `#ui`) so its workers are not woken by other areas' chatter. Every member
  sees `main` plus its subscribed channels; keep area work in area channels and
  reserve `main` for cross-area coordination and final results.

## Addressing

Workers sleep until named: by default a waiting worker wakes only for
`@their-name` (or `@their-prefix` when numbered), `@all`, or `@#<channel>`, and
sleeps through everything else.

- `@name` targets one worker (or all `<name>-1..k` copies in a numbered group).
- `@all` is for swarm-wide rules, decisions, or shared interfaces; never use it
  for routine status.
- `@#channel` wakes every member subscribed to that channel across areas
  (`@#parser is the AST stable?`) instead of `@all`.
- **`@name` is a wakeup doorbell, never a CC.** Every `@mention` wakes that
  agent and consumes a turn. On peer-to-peer handoffs (`author <-> verifier`),
  instruct workers to `@mention` only the next peer who acts, and to tag
  `@coordinator` only when the final deliverable is ready, on a blocker or
  decision, or when no next peer exists.

## Things that will bite

- **Termination (`kill`) is permanent.** A killed worker cannot be revived;
  replacing it requires adding a fresh worker with a new brief. Never kill as a
  pause — a `waiting` worker consumes no tokens.
- **Workers can add helpers.** A worker may spawn helpers for its own scoped
  piece and stays responsible for integrating and reporting upward. Killing a
  parent worker does not automatically kill its helpers, so clean up any left
  behind.
- **Cursors prevent missed posts.** Always pass the highest `#seq` you have
  processed as `since` rather than reading from the live head, so posts sent
  while you were busy are never skipped. Read from `since: 0` if you lose your
  place.
- **Quota pauses need recovery.** When a worker stops on quota exhaustion,
  switch its model in place while keeping its conversation, or re-ping it by
  `@name` once capacity returns.
- **Finish cleanly.** When reporting the finished job to the user, post a final
  `[done] <summary>` line without `@` mentions so monitors and watchers settle.

## Reference

- [Portable board and workers](reference/portable-board-and-workers.md) — implementing swarm lifecycle, board post/read/wait, workspaces, channels, and cursors without host-specific swarm tools.
- [Stall monitor](reference/stall-monitor.md) — optional stall-detection rules, deadlock patterns, 3-alert cap, and dormancy rules.
- [Overview and state](reference/overview-and-state.md) — optional `plan.json` / `view.json` status tracking and UI screenshot format.
