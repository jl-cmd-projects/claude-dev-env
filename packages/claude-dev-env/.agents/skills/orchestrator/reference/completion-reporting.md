# Report completion

Use this procedure before a completion report or an answer about whether work is done.

1. Recover the user's requested outcome and acceptance conditions. Read the evidence for that outcome before choosing its status.
2. Confirm that a fresh `verifier` agent passed the result, per `~/.claude/docs/rule-guides/verified-work.md`. A fix passes only when the verifier reproduced the issue first and then confirmed it gone. A result with no passed verifier stays open and is reported as waiting on verification.
3. Check what each unfinished item changes. Missing deliverables, required verification, necessary approvals, and stated completion prerequisites keep the affected goal open. An administrative item whose absence has no effect on the result, its use, or its acceptance keeps its own task open.
4. State the main outcome first. When that outcome is verified complete and only incidental recordkeeping remains, report the task as complete. A requested status notice alone does not make the main outcome incomplete. Mention the administrative item separately when useful or required by the active reporting rules.
5. Keep unfinished work tracked honestly. When one tracker item combines the completed outcome and unfinished administration, preserve the outcome's goal and evidence, mark its work complete, and keep a separate open administrative follow-up. Do reachable administrative work before ending. Preserve its next action or blocker when it cannot be finished. Never mark it done merely to make the report look complete.
6. Preserve other goals and required delivery. A complete subgoal does not close an unfinished goal or the parent run. Use the goal's acceptance conditions in the [run record](run-state.md) to decide what its remaining work affects.

An administrative action can be requested without being a condition of the main outcome's completion. Treat it as a completion prerequisite when the user states that dependency, when it carries an essential requested result, or when its absence affects the result's usability, safety, or completeness.

For example, a verified report already delivered to the user is complete while an internal progress notice remains unsent. A report still missing required checks, required approval, or its requested delivery remains incomplete.
