# Overview and State

Optional structured status artifacts for tracking multi-worker swarm progress
and visual UI verification without reading raw board logs.

## Coordinator Plan File (`.swarm/plan.json`)

Write `.swarm/plan.json` after adding workers, and update it only when workers
are added, work moves, or the goal changes:

```json
{
  "goal": {
    "title": "Fix split pane layouts",
    "line": "Audit, fix, then verify across both themes."
  },
  "tasks": {
    "auditor": "Audit split panes across states",
    "fixer": "Align split panes in one card"
  },
  "threads": [
    {
      "id": "t-split",
      "title": "Split pane cards",
      "goal": "Panes share one card with clean headers.",
      "tasks": ["auditor", "fixer"]
    }
  ]
}
```

- Keep `goal.title` to 4–8 words and `goal.line` to at most 12 words.
- Group `threads` (1–6 total) by delivered outcome rather than by agent, placing
  every worker in a thread.
- Keep live status, blockers, and asks on the board rather than inside
  `plan.json`.

## Screenshot Reporting for UI Work

When workers make visual or UI changes, instruct them to include screenshots on
their own line inside completion posts:

```text
Screenshot: <path> | <what changed, at most 10 words>
```

Keep the same screen, window size, and theme across before/after captures, using
full-window views without manual crops.

## Narrator Summary (`.swarm/view.json`)

On large swarms where the coordinator needs a dedicated status digest, a
read-only `narrator` worker can watch board updates (never posting to the board
itself) and maintain `.swarm/view.json` with `as_of_seq`, `updated_at`,
`headline`, `phase`, `attention` items, `workstreams`, `milestones`, and `risks`
— citing `#seq` for every claimed state rather than inferring completion.
