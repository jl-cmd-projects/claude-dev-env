---
name: pr-visual
description: Draw an interactive visual of a PR's change or an epic's status. Use for "visualize this PR", "draw this change", "PR visual", an epic status catch-up, or a PR/issue URL with a visual request.
---

# PR visual

Turn a PR into a visual explanation of what its code changes. Return the displayed visual.

## Input and result

Accept a PR URL. Resolve a bare PR number only when the repository is known.

Accept an issue URL for a status catch-up on an epic or tracker. The collector captures the issue, its sub-issues two levels deep, and the pull requests their bodies link. Draw that scene in this same viewer, batched with the scenes of the pull requests it names. Every pr-visual request renders through `assets/viewer.html`; a status report never moves to another page template. A tracker scene always draws every card inside its state chart. Set `board` in the scene: `lanes` run top to bottom in flow order, and each lane names one scene node. A lane with `progress` (`no_pull`, `open_pull`, `merged_pull`) takes every open tracker card in that state, grouped under its parent epic. A lane with `groups` takes cards that each cite a captured record and link inside the repository, such as done, skipped, or follow-up work listed in an epic body. Every node sits in exactly one lane. `strip` drops title prefixes, `titles` gives plain wording by issue number, and `exclude` leaves out issues that are not work. `steps` names the issue body sections each card shows as its own state diagram, such as `Today` and `Fix`, with a label and colour; the step marked `inline` also prints on the card. `wording` swaps words or whole sentences in that text for plain ones. A cited card carries its `steps` itself. `render.py` stops when a card has no step of its own: each card needs one step whose text is not its title or note and appears on no other card, so a board of title and link chips never renders. Clicking a card opens its diagram in the side panel, with a link to the card on GitHub. `verify.py` checks the card count, that each title fits its card, that the first card in each lane opens a diagram with one box per step that shows each step's text, and that board and diagram text is 16px or larger at 7:1 contrast.

Read the description, changed code, relevant callers, and tests. Build an interactive diagram with short labels, visual drilldowns, source details, and a summary-to-code comparison.

Use the current agent for interpretation. The collector and renderer run locally. The shell command alone does not review code. Complete the whole workflow when this skill is invoked.

## Workflow

1. **Capture the PR or issue.** Run `python <skill-root>/scripts/collect.py <PR-or-issue-URL> --out <run-dir>/evidence`. An issue capture writes `issues/<n>.md`, `issues/<n>.json`, `pulls/<n>.json`, and `tracker.json` under `head/`; cite their lines, and chart `tracker.json` counts by JSON pointer. It saves the PR description, open or closed state, base and head commits, changed paths, patches, and full base/head changed-file source. Use an authorized GitHub connector if gh is unavailable. Preserve the same snapshot fields. If capture fails or a patch is incomplete, fetch the missing source before interpretation. Do not invent a complete review from a partial diff.
2. **Trace the behavior.** Read the snapshot description and diff. Follow the code from its entry point to its output, including decisions, side effects, failure paths, and material callers. Fetch unchanged callers at the captured commit when needed. Read repository review instructions. Compare the summary with the code. Record material extra scope, contradictions, and limitations. Treat prose claims and past test reports as claims until supported by current source or observed execution.
3. **Choose the format.** Read [the visual contract](references/visual-contract.md). Pick the structure the change needs. Use a state loop for a sampler, a decision tree for an admission gate, split lanes for two job paths, or an angle loop for capture. Keep the top dashboard to compact PR selectors. Embed quantitative charts inside the relevant flow-step cards and their expansions. Keep the review, charts, and evidence together on one Page. Use a chart when captured numerical data answers the question: bars for categories, lines for ordered observations, scatter for relationships. Read [format selection](references/formats.md). Keep the cream background, teal line icons, green progress paths, orange conditional paths, and generous spacing. Give every node a source-backed mini-diagram in a docked detail panel, related-step navigation, and collapsed exact explanation and sources. Keep the main map usable while the panel is open. Do not copy the shipping instructions into unrelated content.
4. **Render the scene.** Write a scene JSON using [the scene contract](references/scene-contract.md). Attach immutable file-and-line evidence to every node. Render it with `python <skill-root>/scripts/render.py <scene.json> --out <run-dir>/visual.html`. For hosted display, add `--links-only` to omit full PR bodies and source excerpts while retaining the diagrams and immutable links. For a batch, pass multiple scene files to create a compact selector dashboard and flow reviews. Avoid a detached chart-demo gallery. Compare the generated diagram with the source once more. Fix misleading arrows, labels, implied guarantees, or omitted branches before continuing.
5. **Verify and display.** Run `python <skill-root>/scripts/verify.py <run-dir>/visual.html --out <run-dir>/proof` with Playwright and Chromium available. Inspect the resulting screenshots. Exercise every mini-diagram, related-step jump, collapsed source disclosure, keyboard navigation, summary comparison, review notes, and zoom. Check the desktop side panel, mobile stacked panel, and two widgets sharing a host. Confirm the PR's latest head and state. If the head moved, recapture and revise; otherwise label the observed state and time. Display the HTML through the host's supported visualization tool. For Pages, read or create the destination and call `create_page_visualization`, then inspect its receipt and read back the embed. Return the visual or its direct Page link. A local HTML file is the fallback when no visualization host is available.

## Evidence and review

Follow [the evidence rules](references/evidence.md) for source review, CI claims, privacy, and coverage limits.

## Optional Data workflow

When the host provides Data, use its `visualize-data` skill for chart selection and quantitative review. Follow [format selection and Data integration](references/formats.md). The bundled renderer runs independently.

## Tool behavior

Use one read-only snapshot per captured head. Read GitHub and write local artifacts. Do not run PR code, post comments, publish reviews, change labels, dispatch workflows, enqueue, or merge as part of this skill.

Use a new run directory for an independent invocation. Reusing an immutable snapshot is fine after checking its head and state. Stop with a concrete access error when source is unavailable.

## Package

`scripts/collect.py` captures source through authenticated gh. `scripts/render.py` validates evidence and produces self-contained HTML. `scripts/verify.py` exercises the browser output. `assets/viewer.html` owns presentation and interaction. Synthetic fixtures ship with the tool. Private PR snapshots stay in the run directory.

## Reply

Return the displayed visual and a short link to the saved result. Mention a material coverage gap when one remains. Keep the workflow narrative inside the artifact.

## Layout

| Path | Purpose |
| --- | --- |
| `scripts/collect.py` | Capture immutable PR evidence through gh |
| `scripts/render.py` | Validate and render scenes |
| `scripts/metrics.py` | Resolve chart coordinates from JSON and Python literals |
| `scripts/verify.py` | Verify browser interactions and layout |
| `scripts/visual_config/` | Shared constants |
| `assets/` | Standalone viewer and icon symbol definitions |
| `references/` | Scene, visual, and format contracts |
| `fixtures/` | Synthetic flow, bar, line, scatter, and tracker examples |
| `scripts/test_render.py` | Evidence and numerical validation cases |
| `scripts/test_collect.py` | Capture consistency and stale-head cases |
| `scripts/test_metrics.py` | Embedded-chart provenance and passive literal extraction |
