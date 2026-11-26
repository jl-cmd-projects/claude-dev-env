# Portable Board and Workers

How to execute `/e-swarm` in any session using standard subagent, messaging,
file, and git worktree tools when no built-in swarm board runtime is present.

## Mapping the Four Capabilities

| Logical capability | Portable implementation |
|---|---|
| `manage_swarm` | Track roster in `.swarm/roster.json`; spawn workers with the host's subagent tool; isolate authors in `git worktree add` directories under `.swarm/worktrees/<name>` |
| `board_post` | Send via host team/agent messaging if available, or append one JSON line to `.swarm/board.jsonl` with monotonic `seq`, `author`, `channel`, `mentions`, and `text` |
| `board_read` | Read `.swarm/board.jsonl` filtering `seq > since` and visible channels (`main` plus the reader's subscribed channels) |
| `board_wait` | Await subagent completion / incoming messages from the host runtime rather than polling in a tight loop |

## Worker Contract

Include these operating rules in every worker brief:

1. **Ownership:** Work only the files or questions named in your brief.
2. **Board etiquette:** Post interim blockers or peer handoffs using `@<peer>`
   and mark final completion posts with `[done]` right after the `@mention`
   (for example `@coordinator [done] <summary>`).
3. **Citations:** Reference prior board posts by `#<seq>` instead of pasting
   their full text.
4. **Workspace isolation:** When assigned a `share` or `branch` worktree, commit
   changes on your worker branch before posting `[done]` so the coordinator can
   merge or cherry-pick before removing the worktree.

## Worker States

- `waiting`: idle between turns, awaiting a `@name`, `@all`, or `@#channel` post.
- `working`: active subagent turn in flight.
- `stopped`: suspended or exited subagent whose saved context can be resumed on
  a new mention.
- `killed`: permanently retired; clean up its worktree only after landing any
  needed commits.

## Channels and Cursors

- Keep `main` quiet so unrelated workers stay asleep; route area chatter to
  named channels (such as `parser` or `ui`) and archive a channel once its work
  finishes.
- Each member tracks `last_read_seq` locally; pass `since: 0` to replay full
  history from the start of `.swarm/board.jsonl`.
