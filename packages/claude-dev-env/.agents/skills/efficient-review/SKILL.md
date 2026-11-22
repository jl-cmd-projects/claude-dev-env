---
name: efficient-review
description: >-
  Review the current branch from the installed skill. On Claude, the plan
  selects haiku and the slim profile. On any other platform, the running agent
  follows the criteria and picks the model. Triggers: /efficient-review,
  "efficient review", "cheap review".
---

# Efficient review

Review the current branch with the criteria in [reference/criteria.md](reference/criteria.md). From this directory, run `python -m tools.efficient_review plan`. The plan names the runtime. This skill makes no network call.

## Claude

When the plan runtime is `claude`, the model is haiku and the profile is the slim profile in `hooks_constants.haiku_spawn_slim_gate_constants`. Run the printed command and send the review task on standard input. See [reference/criteria.md](reference/criteria.md).

## Other platforms

When the plan runtime is `other`, the model is deferred. The running agent applies [reference/criteria.md](reference/criteria.md) and picks the model.

Every spawn names model and effort as an allowed pair from [Subagent model and effort](~/.claude/docs/rule-guides/subagent-model-effort.md).

## Loop

Check each finding against the code. Fix every one that holds. Before a pull request opens, one pass runs, its fixes go in new commits that are pushed, and the pull request opens with no second pass. On the pull request, three full passes with fixes run, and findings a later pass still reports go into one issue. [The pr-lifecycle review loop](../pr-lifecycle/reference/review-loop-before-merge.md) holds both rules. The steps are in [reference/criteria.md](reference/criteria.md).

## Reading guide

| File | What it does |
|---|---|
| [README.md](README.md) | How a session loads this copy, and the shape of a local job a repository may write. |
| [reference/criteria.md](reference/criteria.md) | The review criteria, the finding block, and the loop. |
| [tools/efficient_review.py](tools/efficient_review.py) | `plan` prints the runtime selection. |
