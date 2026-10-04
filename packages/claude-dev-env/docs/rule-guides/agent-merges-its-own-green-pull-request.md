# The Agent Merges Its Own Green Pull Request

Full text behind [`rules/agent-merges-its-own-green-pull-request.md`](../../rules/agent-merges-its-own-green-pull-request.md).

**When this applies:** Any pull request an agent opened or was asked to drive, once its checks report.

## Rule

The agent that drives a pull request merges it. A pull request that is green, carries no open review thread, and sits at a merge state of `clean` is merged in the same run that brought it there. A merge state of `unstable` counts as `clean` when every check's newest report on the head passes. GitHub also counts the older runs of a check that ran again, so a cancelled run followed by a passing re-run still reads `unstable`. Waiting for the owner to type "merge" parks finished work on the person the work was done for.

Three things stay with the owner, and nothing else does:

- A pull request the owner asked to hold.
- A change the owner said they want to read first.
- A repository whose branch rule requires an approving review the agent cannot give.

Where the branch rule requires zero approvals and one status check, that check is the gate, and the agent merges on its verdict.

Validation is the precondition, and green means every check reported on the exact head commit. A branch rule that requires one status check names the floor a merge needs; a pull request whose other checks are red or still running is held until they report.

## The precondition is mechanical

One command prints the verdict:

```
python packages/claude-dev-env/scripts/agent_merge_check.py <owner>/<name> <number>
```

It prints `MERGE` and exits 0 when the pull request is ready. It prints `HOLD` with the reason and exits 1 for a draft, for a head behind or conflicting with the base, for a required check that is not passing, for a check whose newest report on the head is still running, cancelled, or red, for a head the merge queue ejected for failed checks, and for an open review thread. It exits 2 when the state could not be read.

Each hold reason names its own repair, and each repair belongs to the agent:

| Hold | What the agent does |
|---|---|
| Head behind the base | Merge the base branch in and push |
| Head conflicts with the base | Merge the base branch in, resolve, push |
| A required check is red | Read the failing check, fix it, push |
| A check is red, cancelled, or still running | Fix a red one, re-run a cancelled one, or wait for a running one, then read the verdict again |
| A review thread is open | Answer it, push the fix, resolve the thread |
| Ejected from the merge queue for failed checks on this head | Read the merge_group run, fix the failure, push, then read the verdict again |
| The pull request is a draft | Mark it ready once the checks pass |

## When a gate elsewhere holds the merge command

A session working inside another repository can sit behind that repository's own pre-merge gate, which reads the checkout the session works in and refuses a merge command whatever repository the pull request belongs to. That session hands the merge to the session that owns this repository's pull requests, by message, naming the pull request. The receiving session reads the verdict above and merges. The hand-off carries the work; it never lands on the owner.

## After the merge

Delete nothing by hand. The repository deletes the head branch on merge.

## Sibling rules

| Rule | Role |
|---|---|
| [`git-workflow.md`](../../rules/git-workflow.md) | Open ready for review, and confirm each required context fired after the push |
| [`ci-owns-the-gate.md`](../../rules/ci-owns-the-gate.md) | The gate runs once, and it runs on CI |
| [`correction-lens.md`](../../rules/correction-lens.md) | A correction becomes a control at the highest layer that can hold it |
