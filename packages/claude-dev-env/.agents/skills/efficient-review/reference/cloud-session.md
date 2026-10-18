# Headless or auto from a cloud session

The cloud container has no other Claude accounts, so the review runs on the agent-pc runner.

1. From the checkout that contains `tools/efficient_review.py`, dispatch `.github/workflows/efficient-review.yml` on ref `main`. The job runs only from `main`, so the runner executes the reviewed tool code and never the branch under review. Inputs: `account` (blank means auto), `effort`, `level`, `base`, `ref` (the branch to review), and `repository` (the `owner/name` to review when it is not that checkout). Leave `model` blank.
2. Wait for the run to finish.
3. Read `review.md` from the results branch `efficient-review-results/<run id>-<attempt>`. The branch holds that file and `review.json`. The commit message names the account, the launcher, and the served models. Print the review and the served models.

A review of another repository checks it out with the read token configured for that workflow.

To review a pull request in the checkout that contains the workflow, pass its number as `pull_request` and leave `ref` blank. The run reviews the pull request head, then posts each finding on it as a review thread.

For a pull request in this package's public repository, pass `repository` as `jl-cmd/claude-dev-env` and `pull_request` together. The workflow accepts that repository name. The run posts nothing on the public pull request. When the review lists findings, it dispatches the landing repair with the pull request number and the results branch.
