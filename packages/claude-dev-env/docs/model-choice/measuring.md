Back to [Model choice guides](README.md).

# Measuring model choice

## In brief

Compare models on your own tasks by cost per finished task. Run each candidate pair in its own session, record cost and outcome, and keep the pair that gives the best score for its spend.

**When this applies:** You want to change the default pair for a kind of work, or you want proof that a rung of the [escalation ladder](escalation.md) helps. Test only pairs from [Subagent model and effort](../rule-guides/subagent-model-effort.md).

## Steps

The steps adapt [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/). The article tests each model at two or three effort levels. Here, test only the allowed pairs.

1. Sample tasks from your own work. Give each task an outcome check, such as a test, a build or a script. Decide the check before you read any answer.
2. Run each candidate pair on each task, each run in its own session. A session keeps its own prompt cache, so separate sessions keep caches from mixing.
3. Record the cost of each task. Read token use from `usage`, or from `modelUsage` on the result event of a headless run.
4. Plot score against spend for each pair. Keep a setup that mixes models only when it beats every single-model point.
5. Shadow the winner on a slice of work before you switch the default. Compare its results with the current pair on the same tasks.

## Quick check in a session

For one task, you can compare two models in Claude Code:

- Pick one task from the backlog.
- Run it once on each model. Use `/model` to switch, and start a new session for each run.
- Compare the spend of the two runs with `/usage`.

One task gives a hint. Use the steps above before you change a default.

## Tools in this repo

- [Report task usage](https://github.com/jl-cmd-projects/claude-dev-env/blob/main/docs/guides/task-usage-report.md): record token use, cost and pass or fail for each attempt. The script is [task_usage_report.py](../../scripts/task_usage_report.py).
- [Proof before pull request](../rule-guides/proof-before-pull-request.md): spawn headless runs through the account broker, with `--model` and `--effort` on every call.
- [build-eval skill](../../.agents/skills/build-eval/SKILL.md): design an eval with labeled cases and fixed grading.
- [Subagent effort routing eval](https://github.com/jl-cmd-projects/claude-dev-env/blob/main/.claude/hillclimb/subagent-effort-routing/results.md): a worked example. It runs each case as a fresh headless session and grades the pair that each child ran at. Its metrics are in [metrics.md](https://github.com/jl-cmd-projects/claude-dev-env/blob/main/.claude/hillclimb/subagent-effort-routing/metrics.md).

## What to record

- The task ID, the pair, and the run ID for each attempt.
- The outcome from the check: pass or fail.
- Input, output and cache-read tokens, and the cost.
- The served model from `modelUsage`. A run can serve a model other than the one you named.
