# visual-plan

Get a plan you can skim in seconds, open as deep as you need, and answer in place.

```
/visual-plan clean up the flaky tests in CI
```

Produces one HTML page with three pictures:

| Part | Answers | Shown as |
|---|---|---|
| Grid | What is wrong, what fixes it, how much? | problems, fixes and counts in bands by evidence |
| Decisions | What must you choose? | one row per question, the default marked |
| Path | Where are we, and what comes next? | stages, then numbered steps |

Tap any box to open its card over it: flows, before and after, numbers, checks and records, with the source text in a last Details fold. Hover any item at any depth and press `+` to add a note. Pick your answers, then press **Respond** and paste the one answer back to Claude.

Needs `node` to pack the page into a single file. No other dependencies.

See `skills/visual-plan/examples/flaky-tests.html` for a full plan, and `skills/visual-plan/templates/plan.html` for the blank page.

The shape of this plugin follows html-plan by Thariq Shihipar.
