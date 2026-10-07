# Search before acting on an ask

Full text behind [`rules/search-before-acting.md`](../../rules/search-before-acting.md), which loads in every session as the short form.

## Why it loads in every session

An agent decides what to do in the first turns after an ask arrives. [`prefer-existing-tools.md`](../../rules/prefer-existing-tools.md) and [`build-needs-a-user.md`](../../rules/build-needs-a-user.md) load only when a session touches a script, hook, or manifest path. By then the plan is set. This rule loads at the start, so the search comes before the first log entry, plan, brief, or edit.

## What counts as an ask

Any request for new or changed behavior, a tool, a check, a workflow, a report, a tracker entry, or a plan. A question about how something works is research, and the answer already starts from what exists.

## The stop

When the search finds something that does the ask in full or in part, the agent stops before it logs, plans, delegates, or builds. It sends the user the four-point report from the skill's [`references/report-shape.md`](../../.agents/skills/search-before-acting/references/report-shape.md). The user decides whether the addition goes ahead. When the search finds nothing, the agent says where it looked and continues.

## The pull request gate

The pull request gate reads the body of each new pull request. The body carries an "Existing work" heading. Under it, the author lists what the search found with a link or `file:line`, or states that nothing was found and names the places searched. A body without the section is denied with the steps to write it.

## Related rules

| Rule | What it adds |
|---|---|
| [`prefer-existing-tools.md`](../../rules/prefer-existing-tools.md) | How to pick an outside open-source tool once the local search finds none |
| [`build-needs-a-user.md`](../../rules/build-needs-a-user.md) | The caller, first use, and last manual run a new build names |
