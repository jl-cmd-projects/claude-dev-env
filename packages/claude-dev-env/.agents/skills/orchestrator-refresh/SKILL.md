---
name: orchestrator-refresh
description: >-
  Recover an existing orchestrator's goals, task ownership, and next actions.
  Triggers: /orchestrator-refresh, refresh the orchestrator, resume coordination,
  recover after compaction, recover an orchestration run.
---

# Refresh an orchestrator

## Principle

Recover the ordinary-agent role in [orchestrator](../orchestrator/SKILL.md).
This session is the advisor. The parent remains responsible for its own tasks and every open user goal.
An ordinary refresh works without a scheduler or a gate status file.

## Gotchas

- A supplied run locator selects one root. Another root's latest checkpoint cannot replace it.
- Unknown liveness leaves ownership intact until evidence supports a takeover.
- A missing scheduling gate stops re-arming. It does not prove that the user's goals are complete.

## When this applies

Use for a manual refresh, lost context, a handoff, or a supported wake for an existing run.
Keep current authorization and configured model routing when restoring work.

## Process

1. Read the current message and loaded instructions. Load the orchestrator entrypoint.
2. Resolve the run from its supplied locator or `.orchestrator/active-runs/` under the project directory.
   Read the run record's owner and optional wake metadata first.
   For a recorded one-shot firing, confirm both the invocation's wake identity and current root ownership.
   Immediately run `begin-firing` with its explicit `--status-file` and `--run-slug` through [optional scheduling](../orchestrator/reference/scheduling.md).
   Do this before recovery or task-authority steps can exit. Unknown ownership leaves the latch intact.
   A gate mismatch or missing or invalid state ends that gate attempt. Continue ordinary unresolved work within confirmed ownership.
   Read [recovery](../orchestrator/reference/recovery.md) and reconcile before dispatch.
   Register applicable recovery task seeds once the task authority is accessible.
3. Restore every goal and the parent's follow-up task. Rebuild the short follow list from the task authority.
   Inspect results and live workers. Keep pending approvals and unknown owners visible.
4. Continue permitted next actions. Send consult replies through the [local contract](../orchestrator/reference/consult-the-orchestrator.md).
   Reuse a reachable owner where appropriate. Resolve writer ownership before replacement.
5. Save the updated recovery record. Complete only goals whose acceptance and delivery evidence is present.
   Keep remaining goals open and assign the parent's next action.

A manual refresh does not consume an outstanding wake's latch.
Scheduling remains optional and follows the current runtime's supported automation rules.
Retire only this run's owned wake after the run's completion predicates hold.

## Sub-skills

| Skill | When | Produces | If unavailable |
|---|---|---|---|
| `orchestrator` | Every refresh | Current role and completion predicates | Report the missing entrypoint and stop new dispatch. |

## File index

| File | Purpose |
|---|---|
| `SKILL.md` | Refresh entrypoint. |

## Folder map

This skill uses the sibling orchestrator's recovery, consult, and optional scheduling references.
