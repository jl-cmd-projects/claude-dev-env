# Merge policy

This document states how a change reaches `main` in this repository. It names
the gates in the order they run, says which ones hold the merge and which ones
report only, says who performs the merge, and states the rollback path.

## The gates, in order

| Order | Gate | Holds the merge | Where it runs |
|---|---|---|---|
| 1 | The pull request opens ready for review with a Before and an After in its body | yes | the agent that opens it |
| 2 | The full Python and JavaScript suites run on the pull request | yes | GitHub Actions |
| 3 | The install playtest installs the package into a scratch home and reads the envelopes a session-start hook and a blocking hook return | yes | GitHub Actions |
| 4 | The required status check reports green on the head commit | yes | GitHub Actions |
| 5 | The head is up to date with `main`, because the branch rule is strict | yes | GitHub Actions |
| 6 | Every review thread on the head is answered or resolved by the driving agent | yes | the driving agent |
| 7 | The `Review closure` check reports green on the head commit | yes | GitHub Actions |
| 8 | The merge check reads the live pull request and reports `MERGE` | yes | the driving agent |
| 9 | Advisory findings the follow-up ledger holds | no | the policy lint |
| 10 | Review-bot findings the reviewing bot marks optional | no | the review bots |

Gate 7 goes red while a blocking review finding on the head has no reply and no
resolving push, so a finding holds the merge until the driving agent answers it.
The check runs from the revision `.github/workflows/review-closure.yml` pins.

Gate 8 reads the pull request's live state: out of draft, merge state clean,
and no open review thread. It prints `HOLD` with the repair when one of those
fails, and every repair belongs to the driving agent.

Gates 9 and 10 report and record. A finding there opens its own pull request and
never holds this one.

The [install playtest guide](install-playtest.md) describes its stages and the red-run proof.

## The required status checks

The branch ruleset on `main` requires this context:

```required-status-checks
instruction-pairs / instruction-pairs
```

The branch rule asks for zero approvals and keeps heads up to date, so no human
approval is needed to merge here.

`packages/claude-dev-env/scripts/merge_gate_checks.py` reads the block above
and the branch ruleset, and reports every context named here that the ruleset
stopped requiring.
`packages/claude-dev-env/scripts/test_merge_gate_checks.py` runs that
comparison against the checked-in ruleset snapshot at
[`merge-policy-ruleset.json`](merge-policy-ruleset.json). Refresh the snapshot
with:

```
python packages/claude-dev-env/scripts/merge_gate_checks.py \
  --document docs/merge-policy.md \
  --ruleset docs/merge-policy-ruleset.json \
  --repository jl-cmd/claude-dev-env \
  --refresh
```

## Who merges

The agent that drives the pull request merges it, once the gates above pass.
The branch rule on `main` enables a merge queue, so a merge call can place the
pull request in the queue, and the queue then merges it.

Every PR gets /efficient-review run through Cursor cloud agents, looped until
clean, with all required checks green; then the agent merges it. The owner
never merges. Load the efficient-review skill from the user's dev environment.

No agent overrides a red check. Writes to production systems, to production
databases, and to the owner's machine outside a self-hosted runner job stay
behind the owner's word.

## Opening the pull request

An agent opens the pull request through the route below, and it does not stop to ask the owner for an account.

1. Check the branch from the repository root. Run `python packages/claude-dev-env/scripts/repository_policy.py` and `node packages/claude-dev-env/bin/cde.mjs lint --base origin/main`. Both must exit 0.
2. Push the branch under its own name with `git push origin HEAD:refs/heads/<branch>`. Never push to `main`.
3. Review the branch diff and fix every finding that holds. When a pass reports zero findings, record it for the full 40-character head commit (`git rev-parse HEAD`) with `python ~/.claude/scripts/merge_review_receipt.py <owner>/<repo> open <head sha> 0`. Once the pull request exists, pass its number in place of `open`.
4. Write the body first. It starts with a Before section and an After section, as the first gate above requires, and it carries the proof. The local proof gate does not read a body sent through the workflow, so the proof has to be in the body on its own. Then open the pull request through the app workflow in this repository. Write a JSON file with `"ref": "main"` and an `inputs` object holding `head`, `base`, `title`, `body`, `draft`, `assignee`, and `reviewer`. Send it with `gh api -X POST repos/<owner>/<repo>/actions/workflows/open-pr-as-app.yml/dispatches --input <file>`. A 422 that names an unexpected input means the workflow on `main` lacks that input: drop only that input and send again.
5. The dispatch returns before the workflow opens the pull request. Find the run by its title, `Open a pull request from <branch>`, because another agent's run can be newer than yours: `gh run list --repo <owner>/<repo> --workflow open-pr-as-app.yml --limit 50 --json databaseId,displayTitle --jq '[.[] | select(.displayTitle == "Open a pull request from <branch>")][0].databaseId'`. Then wait for it with `gh run watch <run id> --repo <owner>/<repo> --exit-status`. If the run failed, read its log, and check for an open pull request on the branch before you send again, so a second dispatch does not open a duplicate.
6. Find the number with `gh pr list --repo <owner>/<repo> --head <branch> --state open`. Bind the pull request to the session with the `bind_pr` tool when one is available.
7. Wait for the checks on the head. Fix a red check, push, and record a receipt for the new head. Then merge with `gh pr merge <number> --repo <owner>/<repo> --merge --match-head-commit <head sha>`. If the merge call reports that the pull request joined the merge queue, the queue merges it once its checks pass.

Do not change `GITHUB_DEFAULT_ACCOUNT`, a token, or any other account setting to get past a suspended or invalid account. Report the account to the owner and use the workflow route above.

## Rollback

A merge that has to come out goes back through the same path. The merge handler
thread opens a revert pull request, drives it through the gates above, and
merges it. Nobody pushes to `main` and nobody force-pushes it.
