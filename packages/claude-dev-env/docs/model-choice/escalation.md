Back to [Model choice guides](README.md).

# Escalation ladder

## In brief

When a result is not good enough, first give the agent a way to check its own work. Then raise effort where the model has a step. Then move up one model at a lower effort.

**When this applies:** A task fails or comes back weak on its current model and effort, and you want to try again. Every rung uses a pair from [Subagent model and effort](../rule-guides/subagent-model-effort.md).

## The ladder

The order comes from [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/). The rungs are adapted to the allowed pairs.

1. Add self-verification. Give the agent a test, a build or a script that tells it when the work is done.
2. Raise effort one level, where the model has a step. Haiku steps up through low, medium, high, xhigh and max. Fable steps up from low to medium to high.
3. Move up one model, at a lower effort. Opus and Sonnet have one effort each here, so for them step 2 is this step.

The model rungs, in order:

- Haiku max to Sonnet high.
- Sonnet high to Opus medium.
- Opus medium to Fable low or Fable medium. Start Fable at a lower effort, as the article says.
- Fable medium to Fable high.

To confirm that a rung helps, follow [Measuring model choice](measuring.md).

## Effort before a bigger model

The article says to try effort before you change models. Past high, one more effort level can cost as much as a bigger model.

- In the article's SWE-bench Pro run, Opus at medium scored about 2.5 points below Opus at high, at about 70% of the cost.
- In the same run, Opus at xhigh scored about 1.4 points above high, at about 2.5 times the cost of high.
- In the article's FrontierCode 2.0 run, Fable at high scored 45.3%. Opus at max scored 45.5% at about twice the cost per task.
- In the article's Terminal-Bench 3.0 run, Opus at high scored 58.9%. Fable 5.1 at max scored 58.0% and used about twice the tokens. Max effort added cost and no score.

These numbers fit the allowed pairs, which cap Opus at medium. Medium keeps most of the score for less spend. Past that point, Fable at high gives the same score for less cost.

## Low first, then retry the failures

The article runs every task at low effort, then reruns only the failures at high. That run passed about 97% of tasks at about $0.17 a task. Running every task at high passed 95.3% at $0.29 a task.

Here, run the cheaper pair first, then rerun only the failures on the next pair up:

- Haiku low, then Haiku high.
- Fable low, then Fable high.
- Sonnet high, then Opus medium.
- Opus medium, then Fable.

This works only when a check can tell which tasks failed. Add that check first, as step 1 says.

## Price the hardest tasks

A few hard tasks can drive most of the spend. On one 20-problem benchmark in the article, two problems were 43% of the total spend.

- Record cost per task, and find the tasks that cost the most.
- Put the hardest tasks in the sample when you compare pairs. A sample of easy tasks hides most of the spend.
