---
name: efficient-review
description: >-
  Run one low-cost code review of the current branch, or of a branch in another
  repository, as a headless Claude run on haiku with the slim review profile.
  An auto run lets the account broker pick the account. A headless run names
  the account. Triggers: /efficient-review, "efficient review", "cheap review",
  "haiku review of this branch".
---

# Efficient review

This skill runs one headless code review of a branch on haiku and prints its findings. Pick the mode, run the planner, then run the review on the machine that holds the Claude accounts, or through the agent-pc runner from a cloud session.

Argument shape: `/efficient-review [auto|headless] [account] [model=] [effort=] [level=] [base=]`. Pass `model=` only as the Defaults section allows.
A blank argument comes from [`defaults.json`](defaults.json).

## Defaults

**Always run the review on haiku.** `defaults.json` names `haiku`, and a blank `model` input runs it. Pass `model=` or the workflow's `model` input only when the owner's own message names the family as a directive, such as "run this review on sonnet". Then run it on that family. Do not ask which model to use. Do not change the model on your own, for depth, for cost, or because passes keep finding issues. A stream of findings is a reason to fix the findings and run haiku again.

**The review must run headless.** Never spawn the review as an Agent subagent in this session. A subagent runs inside the parent session, so it cannot load the slim profile's setting sources, plugin folder, MCP config, or auto-compact window. `defaults.json` holds a headless mode, and `load_defaults` refuses any other mode.

## Subcommands

Run each one as `python -m tools.efficient_review <subcommand> <arguments>` from the checkout that contains `tools/efficient_review.py`.

| Subcommand | Action |
|---|---|
| `plan` | Prints the mode, account, model family, harness, effort, level, base, and the prompt. |
| `accounts` | Lists the Claude accounts a headless run can name. |
| `run` | Runs a headless or auto review and prints the review, the served models, and the saved file. |

## Modes

| Mode | Picked when | Account |
|---|---|---|
| auto | No mode word and no account. The word `auto` picks it too. | The account broker picks it. Ask nothing. |
| headless | The word `headless`, or an account launcher name. | Required. With no account named, ask for one. |

A model is a family name: haiku, sonnet, opus, sol, or luna. The planner refuses a versioned model ID. `codex review` takes no level, so the planner refuses `level=` with sol or luna.

## 1. Headless mode with no account

Run `python -m tools.efficient_review accounts`. Ask with the session's question tool, one option per listed account, and wait for the answer. The answer is the account. On the machine that holds the launchers, the list comes from the `claude-*.cmd` launchers, without `claude-base`, `claude-raw`, and `claude-kimi`. In the cloud the list is the known roster.

## 2. Headless or auto on that machine

Run `python -m tools.efficient_review run <arguments> --repository <checkout>`. When the checkout has no launcher folder, go to step 3.

- It builds the slim profile from `tools.review_profile` into a temp folder.
- Auto asks `account_broker.py choose --product claude` for the account.
- It runs the account launcher with `-p`, the model alias, the effort, the profile arguments, and the environment. The system prompt file holds the review rules from the checkout that contains the runner, and the code standards. The prompt and the diff against the base go on standard input.
- A sol or luna family runs `codex review` on the newest slug of that family. The log prints that slug.
- It prints the review, the served models from the stream's `modelUsage` keys, and the saved file. The review and its record go to a temp folder outside the repository.

## 3. Headless or auto from a cloud session

The cloud container has no other Claude accounts, so the review runs on the agent-pc runner. Read [reference/cloud-session.md](reference/cloud-session.md).

## Reading guide

| File | What it does |
|---|---|
| [`reference/cloud-session.md`](reference/cloud-session.md) | Dispatching the review from a cloud session and reading its results branch. |
| [`defaults.json`](defaults.json) | The default model family, effort, level, prompt, base, profile, advisor, validator, mode, and timeout. |

## Common pitfalls

- **Picking a stronger model after several passes.** Fix the findings and run haiku again.
- **Setting a valid finding aside.** Check each finding against the code. Fix every one that holds in the same branch, even when it reaches files the diff did not touch. Answer only the findings that fail the check, with the file and line that rules each out.
- **Asking which model to use.** The answer is haiku. When the owner names another family, run it without a confirmation question.
- **Spawning the review as a subagent.** The review loses the slim profile. Run it headless.
- **Dispatching from the branch under review.** The workflow runs only from `main`.

## Out of scope

- The `validator` default stays `off`.
- A fixer step after the review. The skill has no fixer step.
