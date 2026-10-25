Back to the [rules index](../../rules/index.md).

# Verified work

## In brief

Every piece of work runs in six steps: research, verify the research, plan, verify the plan, implement, verify the fix. A separate `verifier` agent runs each verify step. The fix check reproduces the issue on the old state first, then confirms it is gone on the new state. The user gets only results a verifier passed.

**When this applies:** Any task: a change to code, configuration, rules, or a document, and any finding, cause, or fix reported to the user.

## The six steps

1. **Research.** Find the issue and its cause in primary sources: files, logs, runs, command output. Write each finding as a claim with its source.
2. **Verify the research.** Spawn a fresh `verifier` in research mode. It reports CONFIRMED or REFUTED for each claim, and what the research missed. Fix the research before you plan.
3. **Plan.** List the pieces of the fix.
4. **Verify the plan.** Spawn a fresh `verifier` in plan mode. It reports SOUND or GAP for each piece: does it close part of the researched issue, and does it break a test, a budget, or a constraint. Revise the plan for each GAP.
5. **Implement.** Build the pieces.
6. **Verify the fix.** Spawn a fresh `verifier` in fix mode. It reproduces the issue on the old state, confirms the issue is gone on the new state, and confirms an undo of the fix fails again. When no scratch copy can revert the fix, such as an installed setting, it reports UNDO NOT RUN with the reason, and REPRODUCED plus FIXED still pass. A fix whose issue did not reproduce does not pass.

## The verifier

- The verifier is never the agent that did the work. The spawner is the owner of the work. A fresh agent at each verify step keeps the check apart from the author.
- Its brief gives the issue, the sources, the old state and the new state. It leaves out the worker's conclusion, so the verifier tests the claim and does not inherit it.
- Use the `verifier` agent definition and its brief template. On a host without that agent, give a fresh general-purpose agent the same contract.
- A verifier's own check ends the chain. It runs no research, plan, or verifier of its own.
- A FAIL goes back to the worker with the verifier's evidence. After the next attempt, a new verifier checks it.

## Reporting

Report only what a verifier passed. Name the verifier's verdict and the evidence it produced. A result that no verifier has passed is still work in progress: say that it waits on verification.

## Enforcement

`hooks/routing/spawn_oversight_hook.py` adds the six steps, the separate verifier, the reproduce-first check, and the reporting rule to every spawn at every level of the agent tree whose brief has an `Outcome:` line and an `On a blocker:` line; the hook already denies a brief without them, and the verifier brief template carries both. The flow itself adds context only. No hook refuses a report, a commit, or a spawn for a missing verifier run, so the flow never blocks work the user asked for.
