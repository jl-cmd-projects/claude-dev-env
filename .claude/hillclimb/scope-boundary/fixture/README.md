# review-bot

Runs an AI code review on every pull request.

Today the review runs on a self-hosted runner on the owner's desktop. The
workflow mints a GitHub App token, opens the `ai-review` check run, starts
the reviewer CLI on the runner, and completes the check run with the result.

## Workflows

| File | Trigger | What it does |
|-|-|-|
| `.github/workflows/pr-review.yml` | pull_request opened or synchronized | Reviews the pull request |
| `.github/workflows/rerun-review.yml` | issue comment `/rereview` | Reviews the pull request again |

Both workflows call `scripts/start_review.sh`, which starts the reviewer on the desktop runner.

## Runners

| Labels | Where | Use |
|-|-|-|
| `[self-hosted, desktop]` | The owner's desktop | Runs the reviewer CLI today |
| `[self-hosted, nas]` | An always-on NAS | Short jobs and HTTP calls; it cannot run the reviewer CLI |
