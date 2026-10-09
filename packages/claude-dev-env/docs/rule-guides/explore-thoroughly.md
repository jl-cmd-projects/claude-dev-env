Back to the [rules index](../../rules/index.md).

# Explore thoroughly

## In brief

**When:** Before you log, plan, delegate, or build an ask, or choose an approach.

Search for what already does the ask, in full or in part. When something exists, stop and report it to the user in four points; run the `search-before-acting` skill. Then read files, patterns, and constraints, scaled to risk. Once the files, constraints, and success condition are known, act without repeating settled research.

**Enforcement:** the pull request gate denies a body with no "Existing work" section.

Source: [Anthropic - Overthinking and Excessive Thoroughness](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#overthinking-and-excessive-thoroughness)

Note: This deliberately chooses exploration depth over the "commit and execute quickly" pattern from the same source. Thorough upfront exploration is preferred for the intended workflow.

## Search for existing work first

Before you log, plan, delegate, or build an ask, search for what already does it in full or in part. An ask is any request for new or changed behavior, a tool, a check, a workflow, a report, a tracker entry, or a plan. The `search-before-acting` skill holds the search places, the four-point report, and a playbook for each next move.

When the search finds something, stop before you act and report what exists and where, what it covers of the ask, what is missing, and what the addition would add. When it covers the whole ask, tell the user they already have it. When the search finds nothing, say where you looked and continue.

[`prefer-existing-tools.md`](../../rules/prefer-existing-tools.md) and [`build-needs-a-user.md`](../../rules/build-needs-a-user.md) load only when a session touches a script, hook, or manifest path. This rule loads in every session, so the search comes before the plan is set.

The pull request gate reads the body of each new pull request for an "Existing work" heading. Under it, list what the search found with a link or `file:line` and what the pull request adds on top of it, or state that nothing was found and name the places searched.

## Before committing to an approach

- Read the relevant files. Understand what exists before proposing what to change.
- Map the existing patterns: naming conventions, file organization, architectural decisions.
- Identify constraints that could invalidate an approach before investing effort in it.

## Exploration scales with risk

- Small change to a familiar file: a quick read of the file and its immediate neighbors is enough.
- New feature or cross-cutting change: read broadly across the codebase to understand how similar things are done.
- Architectural decision: explore the full landscape before recommending a direction.

## Inside an autonomous run

The depth budget shrinks once the evidence is in hand. When you can already name the files, the constraints, and what success looks like, further reading buys nothing: act. Re-reading a file to re-derive a fact the run already settled is the shape to cut. See [`long-horizon-autonomy.md`](../../rules/long-horizon-autonomy.md).

## Relationship to other rules

- **research-mode.md** ensures factual claims are grounded. This rule ensures implementation plans are grounded in the codebase.
