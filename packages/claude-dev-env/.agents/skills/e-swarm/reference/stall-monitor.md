# Stall Monitor

Optional helper role for large swarms that detects when all active workers and
the coordinator are parked waiting while the goal remains unfinished.

## Monitor Rules

- **Never do task work:** Leave code edits, builds, reviews, and user replies to
  other members; standard worker completion rules stop applying to the monitor.
- **Post only to break a stall:** Send one short post addressed to one member by
  `@name`. Avoid `@all`, avoid posting to `narrator`, and avoid replying to
  follow-ups.
- **Cite the board:** Name members, sequence numbers (`#seq`), and `since`
  timestamps from `.swarm/board.jsonl` and `.swarm/roster.json`.

## Cadence and Background Scheduling

- Run checks on a **3-minute cadence** (`*/3 * * * *`) using a non-blocking
  background daemon timer so the monitor's schedule never keeps the user's main
  session from appearing idle.
- On startup, read the board from `since: 0` to record `LAST` (highest `#seq`
  seen), schedule the single 3-minute daemon timer, and park with `wake_mode`
  set to `mentions`.
- When resuming after a host restart (when background timers cleared), check
  active scheduled tasks first and re-register one timer if missing so two
  timers never run concurrently.

## Stall Detection Patterns

A swarm is stalled when every live member except the monitor (including the
coordinator) is `waiting` or `stopped` and the job remains unfinished. When any
member is `working`, a long build or turn is still active.

On each tick, catch up with `since: LAST`, inspect roster fields (`state`,
`wake_mode`, `wait_since`, `last_read_seq`, `last_post_seq`, `last_post_time`),
and check five causes in order:

1. **Unaddressed result:** A post landed after the coordinator's `last_read_seq`
   without `@coordinator` -> `@coordinator [stall] #<seq> was addressed to nobody`.
2. **Coordinator has unread posts:** Name unread `#seq`s to `@coordinator`.
3. **Unanswered `@mention`:** A waiting member was named after its
   `last_post_seq` and posted nothing since -> re-ping `@<member> [stall] #<seq> is for you.`
   Escalate to `@coordinator` on a later tick if re-pinging fails (the member
   may be out of quota).
4. **Dependency chain:** Members wait on one another -> report the root blocker
   and `#seq`s to `@coordinator`.
5. **Channel stall:** An unaddressed post in an area channel reaches only that
   channel's subscribers; treat a channel whose members all wait on each other
   as stalled and report the channel, members, and last `#seq` to `@coordinator`.

## Alert Cap and Dormancy

- Skip repeating the same stall alert on consecutive ticks; wait for a state
  change or **three ticks (~10 minutes)**, and stop alerting on a stall after
  three unanswered notices.
- Go dormant when the coordinator posts `[done] ...`, only `monitor` and
  `narrator` remain live, or five consecutive ticks (**~15 minutes**) show no
  `working` members and no new board activity.
- To go dormant, cancel the 3-minute timer and switch `wake_mode` to `all` so
  any new post wakes the monitor; on `@monitor resume` or any wake while
  dormant, re-arm the timer and run a check tick.
