Back to [Model choice guides](README.md).

# Which model for which job

## In brief

Start most work on Opus at medium. Move down to Sonnet or Haiku when the work is well scoped or cheap to check. Move up to Fable when Opus falls short or the work is very large.

**When this applies:** You pick the model and effort for a session, a subagent or a headless run. The allowed pairs are in [Subagent model and effort](../rule-guides/subagent-model-effort.md).

## Starting pair by job

This table adapts [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/). The note says where this repo differs from the article.

| Job | Start here | Note |
| --- | --- | --- |
| Everyday engineering, debugging, features over many PRs | Opus medium | The article raises Opus to high next. Here the next step is Fable. |
| Well-scoped coding, such as a bug fix or a feature built to a spec | Sonnet high | The article starts Sonnet at medium. Here Sonnet runs at high. |
| Classification, routing, tagging, data extraction | Haiku medium | Same as the article. |
| Side-task subagents: file search, log reading, summaries | Haiku through `lean-worker`, or Sonnet high | Adapted. See [Subagents and fan-out](subagents-and-fan-out.md). |
| Chat and interactive work | Sonnet high, or Haiku for simple chat at volume | The article starts Sonnet at low or medium. Here Sonnet runs at high. |
| Everyday docs, slides and sheets | Sonnet high | Use Opus medium for complex financial models or large source docs. |
| Repeated agent tasks: review, investigation, drafting | Sonnet high | The article uses Sonnet at medium. Here Sonnet runs at high. |
| Computer use and vision | Opus medium | Same as the article. |
| Major refactor, migration, architecture, leading many subagents | Fable medium, then Fable high | Same as the article. |
| Deep research, quantitative analysis | Fable medium, then Fable high | Same as the article. |
| You are not sure | Opus medium | Same as the article. |

## Move down

- Move to Sonnet high for well-scoped work, such as bug fixes and features built to a spec.
- Migrations and performance work can still need Opus. A major one can need Fable.
- Move to Haiku for high-volume work that a check can confirm, such as classification, routing and extraction.
- Move to Haiku for subagents that do side tasks. A wrong Haiku answer is cheap to spot.
- Keep small models off long agent loops. They suit short, checkable steps.

## Move up

- Move to Fable for the hardest coding, finance and science work.
- Move to Fable when Opus falls short on a task at the highest effort the [effort levels file](../../hooks/hooks_constants/subagent_effort_levels.json) allows it. The article says "when Opus at high falls short".
- Move to Fable for long runs with no one watching.
- Before you move up, follow the [escalation ladder](escalation.md).

## Prices

Source: the article, Nov 2026. Prices change, so check the current price list before you plan spend.

| Model | Input per million tokens | Output per million tokens | Cache read per million tokens |
| --- | --- | --- | --- |
| Haiku, prompt up to 100K tokens | $0.10 | $0.50 | $0.01 |
| Haiku, prompt over 100K tokens | $0.50 | $2.50 | $0.05 |
| Sonnet | $2 | $10 | $0.10 |
| Opus | $4 | $20 | $0.20 |
| Fable | $8 | $40 | $0.20 |

- Opus costs half of what Fable costs per token.
- Only Haiku has price tiers by prompt length. For long prompts, compare models on cost per finished task. See [Measuring model choice](measuring.md).

## Thinking

- Opus and Fable always think. You cannot turn thinking off on them.
- Sonnet and Haiku use adaptive thinking. They think more on harder steps.
