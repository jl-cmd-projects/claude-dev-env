# Overview and State

Optional structured status files for summarizing swarm progress and visual UI
verification without reading raw board logs.

## Coordinator Plan File (`.swarm/plan.json`)

Write `.swarm/plan.json` once workers are added, and rewrite it only when
workers are added, work moves, or the goal changes:

```json
{
  "goal": {"title": "Fix split pane layouts", "line": "Audit, fix, then verify in both themes."},
  "tasks": {"auditor": "Audit split panes across states", "fixer": "Align split panes in one card"},
  "threads": [{"id": "t-split", "title": "Split pane cards", "goal": "Panes share one card with clean headers.", "tasks": ["auditor", "fixer"]}]
}
```

- Keep `goal.title` to 4 to 8 words and `goal.line` to at most 12 words.
- Group `threads` (1 to 6 total) by delivered outcome, placing every worker in a
  thread, and keep live status, blockers, and asks on the board.

## Screenshot Reporting for UI Work

When workers make visual or UI changes, instruct them to flag screenshots on
their own line inside completion posts:

```text
Screenshot: <path> | <what changed, at most 10 words>
```

Keep the same screen, window size, and theme across full-window captures.

## Narrator Digest (`.swarm/view.json`)

On large swarms, a read-only `narrator` worker can watch board updates
(`wake_mode: all`, never posting to the board itself) and atomically write
`.swarm/view.json` (under 64 KB) with:

- Top-level fields: `version`, `as_of_seq`, `updated_at`, `goal` (`title`,
  `line`), `running_summary` (1 sentence on active tasks), `headline`, `phase`,
  `now` (map of each roster name and `coordinator` to 2 to 5 words, or
  `"Retired"` for killed members), `threads` (1 to 6 outcome groups with `id`,
  `title`, `goal`, `now`, `workstreams`, `attention`), `workstreams` (each with
  `short: {title, line}`, optional `progress: {done, total}`), `attention`,
  `milestones`, `risks`, `feedback_ack` (`{through_seq, text}`), and optional
  `reel` (`frames: [{path, seq, caption}]` for 2 to 24 UI `.png`/`.jpg`/`.jpeg`/`.webp`
  screenshots).
- Closed enums:
  - `workstreams[].state`: `queued`, `active`, `blocked`, `review`, `done`, `failed`.
  - `attention[].kind`: `decision`, `failure`, `review`, `stuck`, `quota`, `error`, `fyi`.
  - `attention[].severity`: `high`, `med`, `low`.
- Citation rule: every item carries a stable `id` (`^[a-z0-9-]{1,40}$`) and
  cites at least one `#seq` or member ref; omit uncited claims.

## User Feedback and Preferences (`.swarm/prefs.md`)

- Relay user UI overview feedback in one short post:
  `@narrator user feedback: <verbatim user words>` (or
  `@narrator user feedback (default): <verbatim user words>` to update defaults).
- Write member names without `@` inside the relayed user text, and relay only
  UI feedback.
- The `narrator` accepts feedback only from coordinator posts matching those two
  prefixes, updates `.swarm/view.json` and `.swarm/prefs.md`, copies clean
  defaults when `(default)` is requested, and records `feedback_ack`.
