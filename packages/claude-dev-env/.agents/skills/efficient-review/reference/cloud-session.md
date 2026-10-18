# Headless or auto from a cloud session

The cloud container has no other Claude accounts, so the review runs on the runner named by the host workflow.

Read [`settings.json`](../settings.json). A file named by the `EFFICIENT_REVIEW_SETTINGS` environment variable overrides it.

1. Dispatch the workflow file `dispatch_workflow_file` with the host's workflow-dispatch tool, on ref `dispatch_ref`. The job runs only from that ref, so the runner executes the reviewed tool and never the branch under review. Inputs: `account` (blank means auto), `effort`, `level`, `base`, `ref` (the branch to review), and `repository` (the `owner/name` to review when it is not the workflow's repository). Leave `model` blank.
2. A blank `dispatch_repository` means the current checkout, and only when that checkout contains the workflow file. This package does not ship that workflow. Set `dispatch_repository` to the `owner/name` whose workflow runs the review.
3. Wait for the run to finish.
4. Read `review.md` from the results branch `<results_branch_prefix>/<run id>-<attempt>`. The branch holds that file and `review.json`. The commit message names the account, the launcher, and the served models. Print the review and the served models.

A review of another repository checks it out with the token in the environment variable named by `read_token_environment`. A blank name means the workflow uses its own checkout token. The variable's name is host configuration. This package does not name a secret.

To review a pull request in the workflow's repository, pass its number as `pull_request` and leave `ref` blank. The run reviews the pull request head. Posting findings is the workflow's job.

To review a pull request in another repository, pass `repository` and `pull_request` together. Pass `hook_owner` and `hook_repository` in settings when the model gate should accept a dispatch only for that repository.
