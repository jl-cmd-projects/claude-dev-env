---
name: efficient-review
description: >-
  Run one low-cost code review of the current branch, or of a branch in another
  repository, as a headless Claude run on haiku with the slim review profile:
  an auto run where the account broker picks the account by default, or a
  headless run on a named Claude account. Triggers: /efficient-review,
  "efficient review", "cheap review", "haiku review of this branch".
---

# Efficient review

This skill runs one headless code review of a branch on haiku and prints its findings. Pick the mode, run the planner, then run the review on the machine that holds the Claude accounts, or through the host workflow from a cloud session.

Argument shape: `/efficient-review [auto|headless] [account] [model=] [effort=] [level=] [base=]`. Pass `model=` only as the Defaults section allows.
A blank argument comes from [`defaults.json`](defaults.json). Host paths, the account roster, and the cloud workflow come from [`settings.json`](settings.json).

## Defaults

Unless the owner named in `owner_display_name` says otherwise:

**Always run the review on haiku.** `defaults.json` names `haiku`, and a blank `model` input runs it. This is non-negotiable. Pass `model=` or the workflow's `model` input only when that owner's own message names the family as a directive, such as "run this review on sonnet". Then run it on that family and do not ask for confirmation. Never ask which model to use. Never change the model on your own, for depth, for cost, or because passes keep finding issues. A stream of findings is a reason to fix the findings and run haiku again.

**The review must run headless.** Never spawn the review as an `Agent` subagent in this session. A subagent runs inside the parent session, so it cannot load the slim profile's setting sources, plugin folder, MCP config or auto-compact window. `defaults.json` holds a headless mode, and `load_defaults` refuses any other mode.

## Settings

[`settings.json`](settings.json) holds the host values. The `EFFICIENT_REVIEW_SETTINGS` environment variable names a JSON file that overrides it. Neutral defaults are empty lists and empty repository fields.

| Key | Default | Role |
|---|---|---|
| `owner_display_name` | `the owner` | The person whose newest message may name another model family. |
| `excluded_accounts` | `[]` | Launcher names left off the `accounts` list. |
| `known_accounts` | `[]` | Roster the accounts command prints when the machine has no launchers. |
| `broker_relative_parts` | `.claude/scripts/account_broker.py` | Broker path under the home directory. |
| `launcher_directory_parts` | `.local/bin` | Launcher directory under the home directory. |
| `launcher_prefix` | `claude-` | Launcher file prefix. |
| `launcher_suffix` | `.cmd` | Launcher file suffix. |
| `launcher_home_pattern` | a `CLAUDE_CONFIG_DIR` assignment | Pattern read from a launcher file. |
| `codex_catalog_module` | empty | Python module whose `discover_model` resolves a sol or luna slug. Required for those families. |
| `rules_root` | empty | Directory whose `rules_paths` are the review rules. Empty walks parents of this skill for the first match. |
| `rules_paths` | `docs/review/review.md` | Rule files read from `rules_root` for every review, whichever repository is reviewed. |
| `dispatch_repository` | empty | `owner/name` whose workflow runs a cloud review. Empty means the current checkout, and only when it contains the workflow file. |
| `dispatch_workflow_file` | `efficient-review.yml` | Workflow file to dispatch. This package does not ship that workflow. |
| `dispatch_workflow_id` | empty | Optional numeric workflow id the model-gate command accepts. |
| `dispatch_ref` | `main` | Ref the workflow runs from. |
| `results_branch_prefix` | `efficient-review-results` | Branch prefix that holds `review.md`. |
| `read_token_environment` | empty | Environment variable name of the token that checks out another repository. Empty means the workflow's own token. |
| `hook_owner` | empty | When set with `hook_repository`, a dispatch must name this owner. |
| `hook_repository` | empty | When set with `hook_owner`, a dispatch must name this repository. |
| `hook_dispatch_tool` | the GitHub workflow trigger tool | Tool name the model-gate command watches for a dispatch. |
| `hook_shell_tools` | `Bash`, `PowerShell` | Shell tools the model-gate command watches. |

## Subcommands

Run each one as `python -m tools.efficient_review <subcommand> <arguments>` from this skill directory.

| Subcommand | Action |
|---|---|
| `plan` | Prints the mode, account, model family, harness, effort, level, base and the prompt. |
| `accounts` | Lists the Claude accounts a headless run can name. |
| `run` | Runs a headless or auto review and prints the review, the served models and the saved file. |

## Modes

| Mode | Picked when | Account |
|---|---|---|
| auto | No mode word and no account. This is the default on the machine that holds the accounts and in the cloud. The word `auto` picks it too. | The account broker picks it. Ask nothing. |
| headless | The word `headless`, or an account name returned by `accounts`. | Required. With no account named, ask for one. |

A model is a family name: haiku, sonnet, opus, sol or luna. The planner refuses a versioned model ID. `codex review` takes no level, so the planner refuses `level=` with sol or luna.

## 1. Headless mode with no account

Run `python -m tools.efficient_review accounts`. Ask with `AskUserQuestion`, one option per listed account, and wait for the answer. The answer is the account. On the machine that holds the launchers, the list comes from the launcher files named in settings, minus `excluded_accounts`. When that directory has no launcher, the list is `known_accounts`.

## 2. Headless or auto on that machine

Run `python -m tools.efficient_review run <arguments> --repository <checkout>`. When the checkout has no launcher folder, go to step 3.

- It builds the slim profile from `tools.review_profile` into a temp folder.
- Auto asks the broker at `broker_relative_parts` to `choose --product claude` for the account.
- It runs the account launcher with `-p`, the model alias, the effort, the profile arguments and the environment. The system prompt file holds the review rules from `rules_root` and the code standards. The prompt and the diff against the base go on standard input.
- A sol or luna family runs `codex review` on the newest slug of that family, from `discover_model` in `codex_catalog_module`. The log prints that slug.
- It prints the review, the served models from the stream's `modelUsage` keys, and the saved file. The review and its record go to a temp folder outside the repository.

## 3. Headless or auto from a cloud session

The cloud container has no other Claude accounts, so the review runs on the host runner. Read [reference/cloud-session.md](reference/cloud-session.md) for the dispatch, the results branch, and the pull request inputs.

## Reading guide

| File | What it does |
|---|---|
| [`reference/cloud-session.md`](reference/cloud-session.md) | Dispatching the review from a cloud session and reading its results branch. |
| [`defaults.json`](defaults.json) | The default model family, effort, level, prompt, base, profile, advisor, validator, mode and timeout. |
| [`settings.json`](settings.json) | Host roster, rules root, dispatch target, and model-gate command scope. |
| [`tools/efficient_review.py`](tools/efficient_review.py) | `plan` reads the arguments, `accounts` lists the accounts, `run` runs a headless or auto review. |
| [`tools/efficient_review_request.py`](tools/efficient_review_request.py) | Reads the defaults and the arguments into one review request. |
| [`tools/efficient_review_launch.py`](tools/efficient_review_launch.py) | Builds the system prompt and the launcher command for one review. The system prompt asks for confirmed findings only, with no minimum count, in a closing JSON block. |
| [`hooks/efficient_review_model_gate.py`](hooks/efficient_review_model_gate.py) | Model-gate command a host registers as PreToolUse. It covers a review dispatch or a `run` command on any family but haiku, unless the owner's newest message names that family as a directive. |
| [`hooks/efficient_review_model_gate.sh`](hooks/efficient_review_model_gate.sh) | Shell command a host points PreToolUse at, so the model-gate command sees the tool call. |

## Common pitfalls

- **Picking a stronger model after several passes.** Fix the findings and run haiku again. The model-gate command refuses the switch when it is registered; a session whose host did not register the hook applies this rule itself.
- **Setting a valid finding aside.** Check each finding against the code. Fix every one that holds in the same branch, even when it reaches files the diff did not touch or reads as a separate cleanup. Answer only the findings that fail the check, with the file and line that rules each out.
- **Asking which model to use.** The answer is haiku. When the owner names another family, run it without a confirmation question.
- **Spawning the review as a subagent.** The review loses the slim profile. Run it headless.
- **Dispatching from the branch under review.** The workflow runs only from `dispatch_ref`.

## Out of scope

- The `validator` default stays `off`. A graded comparison found fewer planted bugs after validation and a higher cost per review, and a fixer on the strict prompt cut false fixes further than validation did (3.5 against 3.8 of 7 bugs, $0.12 more per review, 27% against 52% false fixes).
- A fixer step after the review. The skill has no fixer step.
- The account roster is `known_accounts` in settings, empty until the host fills it.
