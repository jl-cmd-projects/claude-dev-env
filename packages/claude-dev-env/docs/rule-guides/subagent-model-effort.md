Back to the [rules index](../../rules/index.md).

# Subagent model and effort

## In brief

Every agent you start runs on an Anthropic model at an allowed effort. Opus runs at medium. Sonnet runs at high. Fable runs at low, medium or high. Only Haiku runs at xhigh or max. Name the model and the effort on every spawn.

**When this applies:** Every time one agent starts another on a Claude host. That covers the Agent and Task tools, a thread or session spawn, a Workflow agent, an advisor bind, and a headless `claude -p` run.

## Allowed pairs

| Model | Effort |
| --- | --- |
| Opus | medium |
| Sonnet | high |
| Fable | low, medium or high |
| Haiku | low, medium, high, xhigh or max |

- Use Anthropic models only.
- xhigh and max are for Haiku only.
- Any pair outside the table is out.
- One exception: an advisor that is not the built-in advisor tool runs on Opus at high. The built-in advisor follows the `advisorModel` setting.

Codex spawns follow their own policy in [Automatic child model choices](../subagent-model-routing.md).

## Rule

- Name both the model and the effort. A spawn that leaves either one out takes the parent's, and an Opus parent at high hands the child Opus high.
- A fork always takes its parent's model and effort. Fork only from a parent whose own pair is in the table.
- For `claude -p`, pass the pair as flags, such as `--model claude-opus-5-5 --effort medium` or `--model claude-sonnet-5-5 --effort high`.
- When a brief, skill, hook, setting or default gives a pair outside the table, use the allowed pair for that model and say so in your report.

## Which model gets which work

Opus and Sonnet have one effort each here, so pick the model by the work.

- Haiku: finding files, reading logs, running tests, summing up, and sorting or pulling data out of many items. A Haiku mistake is cheap to spot.
- Sonnet: well-scoped work, such as a bug fix or a feature built to a clear spec.
- Opus: code edits, judgment calls, and decisions that rest on what other subagents report.
- Fable: the hardest work, such as a large migration, planning a design, leading many subagents, or a long run with no one watching.
- Keep the costly model's context lean. Cheaper subagents do the long reading and hand back a short summary.
- Before you move work to a bigger model, give the agent a way to check its own work, such as a test, a build or a script.
- A built-in agent such as Explore runs on the session's model unless the spawn names one, so name the model.

Source for the work split: [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/).
