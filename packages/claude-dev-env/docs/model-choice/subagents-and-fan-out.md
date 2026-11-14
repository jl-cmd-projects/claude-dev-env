Back to [Model choice guides](README.md).

# Subagents and fan-out

## In brief

A subagent bills at its own model's rate, so side work on a small model costs less. Keep small models on work that is cheap to check, and keep code edits and judgment on the lead's model. For work bigger than one context window, a top-tier lead can split the task across many cheaper workers.

**When this applies:** You start a subagent, or you plan a task too big for one context window.

## Put side work on smaller models

The source is [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/).

- Small models suit search, test runs, log reading and summaries. A wrong answer there is cheap to spot.
- Code edits and judgment calls stay on the lead's model.
- The subagent hands back a short summary. The lead's context stays small, as [Context and caching](context-and-caching.md) explains.

## How this repo does it

The allowed pairs are in [Subagent model and effort](../rule-guides/subagent-model-effort.md). The hooks are in [Spawn routing](../../hooks/features/spawn-routing.md).

- Name the model and the effort on every spawn.
- Agent definitions carry no `model` key, and `effort` is no frontmatter key.
- A Haiku spawn in a session uses `subagent_type` `lean-worker`. Other Haiku work runs headless through the account broker slim profile.
- The effort route hook fills in an allowed effort when a spawn leaves it out or names one outside its model's list.
- A built-in agent such as Explore runs on the session's model unless the spawn names one. Name the model on every Explore spawn.

The article sets `model: haiku` in agent frontmatter, defines a custom Explore agent on Haiku, and sets `CLAUDE_CODE_SUBAGENT_MODEL`. This repo uses none of them. For the same goal, spawn `lean-worker` with model `haiku` for search, log reading, test runs and summaries.

## Model aliases

- The `haiku` alias is Haiku 5.5 on the Anthropic API from Claude Code v2.1.293.
- On Bedrock, Google Cloud, Microsoft Foundry and Claude Platform on AWS, `haiku` is still Haiku 4.5.
- `ANTHROPIC_DEFAULT_HAIKU_MODEL` pins the alias to one model.
- `opusplan` plans with Opus and executes with Sonnet. That is the opposite of the article's advice. Measure it before you make it a default, as [Measuring model choice](measuring.md) shows.

## Fan-out for bulk work

For work bigger than one context window, a top-tier lead splits the task across many cheaper workers and merges the results.

- In the article's defect search over about 22M tokens, an Opus lead with up to 25 parallel Sonnet workers cost about a third less than Opus alone. The score was the same.
- The article ran both at default effort. Here the lead is Opus or Fable, and the workers are Sonnet or Haiku, each at an effort the [effort levels file](../../hooks/hooks_constants/subagent_effort_levels.json) allows.
- Skip fan-out for one chain of dependent steps, or for work that fits one context.
- The lead stays open until every worker's result is merged. Read [Workers done before complete](../rule-guides/workers-done-before-complete.md).
- For a long run with no one watching, read [Long-horizon autonomy](../rule-guides/long-horizon-autonomy.md).
- The [orchestrator skill](../../.agents/skills/orchestrator/SKILL.md) gives the steps for a lead.

## Advisor pairs

- In the article, none of four advisor pairings clearly beat the executor alone.
- An Opus high executor with a Fable 5.1 advisor scored 90.1% at $2.92 an attempt. That is 1.7 points above Opus alone, for about 2.1 times the cost.
- Measure how often the executor consults the advisor before you add one.

The call rules are in [Advisor tool](../references/advisor-tool.md). The advisor exception is in [Subagent model and effort](../rule-guides/subagent-model-effort.md).
