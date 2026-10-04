# Workers done before complete

Full text behind [`rules/workers-done-before-complete.md`](../../rules/workers-done-before-complete.md).

## The completion gate

The gate applies to subagents, workflow agents, and background shells spawned by a task. The run state can be `state.json`, `pr-converge-state.json`, a task list, or another record the task keeps. A finished worker with an unmerged result leaves the task open.

The gate controls task status. Work that can proceed while a worker runs continues. A worker that dies or hangs becomes a finding to record and report. A wakeup returns the run to the outstanding workers.

## Checklist before marking complete

| Check | Action |
|---|---|
| Are any spawned workers still running? | List them. If any run, stay `in_progress` and schedule a wakeup. |
| Did every finished worker return a result? | Read each result. Report a dead or hung worker as a finding. |
| Is each result merged into run state? | Write it to the run record before closing. |
| Does the task's goal hold? | Check the merged state and the repository or diff behind worker claims. |

The file list, count, description, and finding in each worker report need repository and diff evidence before they enter run state or a user report.

## Examples

An audit task has two workers still running. The lead lists them, keeps the task `in_progress`, and schedules a wakeup to collect their results.

A worker crashes while the others finish. The lead records the crash as a finding, reports it, and keeps the task open until the missing work is covered.

## Relationship to other rules

The [long-horizon-autonomy guide](long-horizon-autonomy.md) covers acting on available evidence and finishing owed work before ending a turn. This gate defines the completion condition for tasks with workers.
