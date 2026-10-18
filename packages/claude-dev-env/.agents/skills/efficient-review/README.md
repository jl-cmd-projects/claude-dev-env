# How a host loads this copy

This package holds the one copy of efficient-review, at `packages/claude-dev-env/.agents/skills/efficient-review/`. A fresh install copies that directory to `~/.claude/skills/efficient-review` and `~/.agents/skills/efficient-review`. Do not keep a second copy of the skill, the runner, or the model-gate command beside it.

## A local session

Run `python -m tools.efficient_review` from the installed skill directory. The working directory is on the module path, so `tools` imports. The same command runs from a checkout of this repository at a pinned commit: the skill directory in that checkout is `packages/claude-dev-env/.agents/skills/efficient-review`. Set `PYTHONPATH` to the skill directory when the working directory is somewhere else.

When `rules_root` is empty, the runner walks parent directories of the skill for `docs/review/review.md`. A checkout of this repository finds that file. An installed copy under a home directory does not, so the host sets `rules_root` to the directory that holds the review rules.

The shell file `hooks/efficient_review_model_gate.sh` is the command a host registers as PreToolUse. This package does not register it.

## A cloud session and a continuous-integration job

A cloud session dispatches the workflow named by `dispatch_workflow_file`, on ref `dispatch_ref`, in the repository named by `dispatch_repository`. Read [reference/cloud-session.md](reference/cloud-session.md). This package does not ship that workflow.

The job that runs the review checks out this repository at a pinned commit, or uses the installed skill directory on the runner, and runs `python -m tools.efficient_review` from that skill directory. It does not run a copy of the runner that lives in the repository under review.

## Where a repository keeps its own settings

The shared `settings.json` stays at the neutral defaults. A consuming repository keeps its own settings file and sets `EFFICIENT_REVIEW_SETTINGS` to that file. Keys in the file override the shared defaults. The rest stay empty.

That file holds the roster, the excluded accounts, the broker path, the launcher names, the codex catalog module, `rules_root`, the dispatch repository, the workflow file name, the workflow id, the ref, the results branch prefix, the environment variable name of the checkout token, and the model-gate owner and repository. Leave those host values out of the shared copy.

## What the consuming repository deletes

Delete the vendored skill and the runner modules the shared copy now contains:

- `.claude/skills/efficient-review/`
- `tools/efficient_review.py`
- `tools/efficient_review_launch.py`
- `tools/efficient_review_request.py`
- `tools/config/efficient_review_constants.py`
- `.claude/hooks/efficient_review_model_gate.py`
- `.claude/hooks/efficient_review_model_gate.sh`
- `.claude/hooks/config/efficient_review_model_gate_constants.py`

Also delete a vendored slice of `tools/review_profile`, `tools/review_command`, `tools/review_rules`, `tools/review_stream`, and `tools/review_codex` when that slice exists only so this runner can import it.

Keep the workflow file, the runner labels, the secret names, the account roster, the review rules, and the codex catalog module. Keep `tools/review_model_eval` when the repository still grades reviews with it. Point the workflow at the pinned checkout or the installed skill directory.
