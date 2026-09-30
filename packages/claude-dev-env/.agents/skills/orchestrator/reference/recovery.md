# Recover goals after context loss

Use this procedure after compaction, handoff, parent replacement, or a gap in ownership evidence.
Re-read current instructions. A summary helps locate evidence but cannot replace it.

## Locate the run

Start with the supplied project directory and loaded orchestrator instructions.
Read its `.orchestrator/active-runs/` locator files, or the explicitly configured registry home.
Read every locator's run ID and owner before selecting a root.
A supplied run ID selects its matching record. With several roots and no selected ID, inspect each without taking ownership.
Continue only work whose run and authority are unambiguous.
Keep each root's goals, workers, approvals, and schedules separate.

Read the selected run record, task authority, and referenced assignments or evidence needed for the next decision.
Use the stable run path even when a pstack latest pointer names another root.
An optional pstack checkpoint is a dated snapshot. Use the registry and task authority for current state.

If the locator is missing, use an exact run path in current instructions, the user message, or verified runtime startup data.
Inspect existing project run directories for recovery evidence before creating a new run.
Reconstruct missing fields from trusted user messages and checked artifacts. Mark unresolved fields as unknown.
Do not infer approval, completion, or absence of a live worker from a missing file.

## Reconcile before writing or dispatch

Register the task seeds below in the selected authority once it is accessible.
If the authority is unavailable, retain the durable intent and follow the recorded recovery method.
An import into a replacement store requires evidence that two parents will not write the same run.

Check the current checkout, artifact revisions, worker listings, and pending actions through available read tools.
Record observation times. Reconcile mismatches in the task authority, then refresh the derived follow list.
Completed worker output still needs the parent's acceptance review.
Reopen a stale completion claim when its evidence fails to cover the current artifact.

Unknown liveness keeps the existing owner and its path reservation.
Use available status or contact tools within their authorization limits to seek evidence.
Continue independent work that cannot overlap the uncertain owner.
Replace a writer only after its termination is confirmed or a supported exclusive takeover establishes ownership.
Preserve partial work and give the replacement its original assignment plus checked partial results.
Parent takeover follows the same rule. Context loss alone does not end the previous parent's process.

Restore pending approvals with their source, scope, and pending action.
Keep an unanswered decision pending even when a checkpoint suggests a default.
Granted authorization carries forward only within its recorded scope and current rules.
When the source is unavailable, continue independent preparation and recover the source before the dependent action.

Compare every goal's acceptance conditions with its task evidence.
Keep the parent follow-up open until all goals and required delivery are resolved.
Answer a status question from this reconciled state without replacing the work.
When one goal completes, update that goal and continue the remaining goals.

## Checkpoint and continue

Save the reconciled run record and update only this root's locator.
Record unresolved gaps and the next permissible action for each open goal.
Retain historical snapshots as evidence with observation times.
Read back the saved pointers before dispatching new work.
Use [scheduling](scheduling.md) only for an owned, supported wake that the current request authorizes.

## Recovery task seeds

1. Resolve the selected root and its task authority from discoverable files.
2. Reconcile all user goals, parent follow-up, workers, and artifact evidence.
3. Restore decisions and approvals with their scope and source.
4. Save recovery gaps and continue the permitted next actions without overlapping owners.

## Verify recovery behavior

Give a fresh verifier only the project directory and the instructions a new session receives.
Ask it to find two active roots, each with separate run records and task authorities.
Include an overwritten latest pointer, a stale snapshot, an unknown worker, and a pending approval.
Include two goals in one root and the parent's own follow-up task.
Check that it preserves ownership and pending approval while naming independent work it can continue.
Ask a status question, then provide evidence completing one goal. Check that the remaining goal stays open.
Use isolated fixtures and permitted read-only tools. Report fixture behavior separately from runtime hook activation.
