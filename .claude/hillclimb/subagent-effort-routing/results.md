# Results, Nov 11 2026

36 sessions per arm: 18 cases, 2 reps each. Parent on Opus 5.5 at high. Every session spawned at least one agent.

| Group | Baseline: ran in rule | v1: ran in rule | v1: hook changed the spawn |
| --- | --- | --- | --- |
| Asks for a pair outside the rule (12) | 0/12 | 12/12 | 12/12 |
| Asks for an allowed pair (8) | 8/8 | 8/8 | 0/8 |
| Names no model or effort (16) | 16/16 | 16/16 | 8/16 |
| All (36) | 24/36 | 36/36 | 20/36 |

What the numbers say:

- Without the hook, an agent does what the ask says. Every ask for Opus at high, xhigh or max, Sonnet at low or medium, or Fable at max ran exactly that way.
- With the hook, every child ran at an allowed pair. Opus asks ran at medium, Sonnet at high, Fable max at high.
- When the ask named no model, the parent always picked one itself, mostly Haiku for Explore or Sonnet at high. No child in either arm inherited Opus at high, so this set never hit that gap.
- The 8 hook changes in that group set an effort on a Haiku spawn that named none. The child ran at medium either way.
- The rule text changed little on its own: spawns that named an allowed pair went from 15/36 to 16/36. The rule is scoped to agent, skill, hook and workflow files, so it does not load in this fixture project.
- Cost per arm: $10.31 baseline, $6.25 v1, from each session's reported total.
