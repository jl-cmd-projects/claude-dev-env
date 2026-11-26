# Portable Board and Workers

How to execute `/e-swarm` in any session using standard subagent, messaging,
file, and git worktree tools when no built-in swarm board runtime exists.

## Mapping the Four Capabilities

| Capability | Portable implementation |
|---|---|
| Swarm management | Maintain `.swarm/roster.json`, spawn subagents via the host subagent tool, and isolate authors with `git worktree add` under `.swarm/worktrees/<name>` |
| Board posting | Use host agent messaging when available, or append one JSON object per line to `.swarm/board.jsonl` |
| Board reading | Read `.swarm/board.jsonl` filtered by `seq > since` and channels visible to the reader (`main` plus subscribed channels) |
| Board waiting | Wait for subagent completion or incoming host messages before advancing |

## Schemas

### `.swarm/board.jsonl`

Each line records one post:

```json
{"seq": 1, "timestamp": "2026-11-26T12:00:00Z", "author": "coordinator", "channel": "main", "mentions": ["parser"], "text": "@parser Own src/parser.rs..."}
```

- `channel` defaults to `"main"` when omitted.
- Workers start their completion posts with `[done]` right after `@<target>`
  (for example `@coordinator [done] Parser cases pass`).
- Cite earlier posts by `#<seq>` when passing context between members.

### `.swarm/roster.json`

Track each member with:

- `name`: short lowercase unique identifier (`all` and `coordinator` are reserved).
- `state`: `waiting`, `working`, `stopped`, or `killed`.
- `workspace`: `inherit` (shared working copy for readers/verifiers), `share` (separate worktree), or `branch` (isolated clone).
- `channels`: array of subscribed area channels (`main` is always visible).
- `wake_mode`: `mentions` (default; wake only on `@<name>`, `@<prefix>`, `@all`, or `@#<channel>`) or `all` (wake on any post in `main` or subscribed channels).
- `wait_since`, `last_read_seq`, `last_post_seq`, `last_post_time`: integer sequence cursors and ISO timestamp used for stall detection and catch-up reads.

## Sharding, Forking, and Model Recovery

- **Numbered pools:** When the user asks for `n` copies or per-item `tasks`
  under one role, name members `<name>-1` through `<name>-<k>`. `@<name>` and
  retiring `<name>` target the whole pool; `@<name>-1` targets one member.
- **Warm context (`fork`):** Seed a new worker from an existing member's (or the
  coordinator's) conversation history when branching research or replacing a
  retired worker.
- **Quota switching:** List live `quota_remaining` and `quota_resets` when
  available. Switch a `waiting` member's model in place while keeping its
  conversation history, and state why when switching. Wait for a `working`
  member to finish its turn before switching it. Re-ping paused members by
  `@name` once capacity returns.

## Channels and Wake Modes

- **Channel operations:** Support `create` (with `channel` and `topic`),
  `subscribe` and `unsubscribe` (by `channel` and `name`), `list` (topics,
  creators, subscriber counts), and `archive` (locks new posts while keeping
  history readable).
- **Channel assignment:** Assign `channels` when adding a worker; its initial
  brief posts to its first channel, which becomes its default reply channel. Any
  helper a worker spawns inherits its parent's channels unless specified
  otherwise.
- **Catch-up rule:** A worker newly subscribed to an existing channel sees
  posts from that moment onward; instruct it to read from `since: 0` on that
  channel when it needs prior history.
- **Addressing constraints:** `@#main` is invalid (use `@all` to reach every
  member). Channel chatter stays in area channels so `main` carries only
  cross-area decisions and final deliverables.
- **Wake modes:** Set `wake_mode` to `mentions` (default) for workers waiting
  on targeted assignments, and set `wake_mode` to `all` when a coordinator or
  monitor needs to wake on every visible post (such as a dormant monitor waking
  on any activity).
