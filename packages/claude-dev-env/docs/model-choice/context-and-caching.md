Back to [Model choice guides](README.md).

# Context and caching

## In brief

Every turn resends the whole context, so a long context costs money on every turn. Keep the costly model's context small and let cheaper subagents do the long reading. Switch the main model only at a natural break, because the prompt cache belongs to the model that wrote it.

**When this applies:** A long session, a lead agent that reads a lot, or a plan to change the session's model partway through.

## Context costs every turn

The source is [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/).

- The API keeps no state. Each turn sends the full conversation again.
- On a long run, most input bills as cache reads. The article gives about $0.03 a turn at 150K context and about $0.004 at 20K.
- Keep the costly model's context for decisions. Cheaper subagents do the long reading and hand back a short summary. [Subagents and fan-out](subagents-and-fan-out.md) shows how to spawn them here.
- Haiku is the only model with prompt-length price tiers. Its price goes up above a 100K prompt. When prompts are long, compare models by cost per finished task. [Measuring model choice](measuring.md) shows how.

This package's `settings.json` sets `autoCompactWindow` to 350000. Haiku 5.5 and Haiku 4.5 compact at 250000 through `modelSettings`.

For cache layout, such as a stable prefix first and new content appended, read the cache section of the [harnessing inventory](https://github.com/jl-cmd-projects/claude-dev-env/blob/main/docs/references/anthropic-harnessing-claudes-intelligence-technique-inventory.md).

## Switching models

- The prompt cache belongs to the model that wrote it.
- The first turn on a new model pays the cache-write price on the full conversation.
- Switch only at a natural break, such as the end of a plan or a finished step.
- Run `/compact` first, or start the new model with a short summary.
- For cheaper side work inside one session, spawn a subagent. The main model and its cache stay as they are.

## Thinking blocks across models

The API reads earlier thinking only when the new model can read the old model's blocks.

| New model | Reads thinking from |
| --- | --- |
| Opus 5.5 | Sonnet and Haiku |
| Sonnet 5.5 | Haiku |
| Fable 5.2 | Opus, Sonnet and Haiku |

- A move down a tier loses the earlier reasoning.
- A move away from Fable 5.2 drops its reasoning.
- The API drops blocks the new model cannot read. The request still succeeds.

A script that keeps its own history has more to check. Read [API compatibility](api-compatibility.md).
