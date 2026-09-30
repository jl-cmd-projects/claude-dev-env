# Consult the orchestrator

The orchestrating session is the advisor.
The human operating that session decides choices reserved by the current authorization rules.

## When an executor consults

Consult after orientation and before the first write when the assignment requires that gate.
Consult before committing to a nontrivial interpretation, before a hard-to-reverse action,
when the same failure repeats, when the approach changes, and when completion evidence is ready.

The first consult carries the assignment, desired outcome, constraints, current evidence,
live decision, unresolved risk, and paths the parent needs to inspect.
Later consults carry changed evidence and the result of the previous guidance.
Keep logs and detailed output in linked artifacts.

## Send through an authorized route

Use the parent identity and contact route recorded in the assignment.
On Claude Code, use its exposed in-session messaging tool.
On Codex, use the available in-session agent transport.
Cross-thread or external messaging follows the runtime's separate authorization rules.
When no authorized route exists, return the consult through the normal task result.

## Reply with one signal

- ENDORSE accepts the approach or checked result within scope.
- CORRECTION names the defect or missing evidence and the needed correction.
- PLAN gives the revised next steps.
- STOP names the blocker and the evidence that prevents dependent work.

Guidance stays within the user's goal and current instructions.
The executor checks scope and permission before acting on any reply.
After CORRECTION or PLAN, report the result before repeating the same question.
On STOP or an unreachable parent, preserve partial work and return the blocker.
Stop the dependent action and continue independent assigned work when permitted.

## Escalate the unresolved choice

The parent answers from the current goal, assignment, and checked evidence.
For a choice that only the user can make, record the pending action and ask once.
Continue independent preparation while waiting. A recommendation does not grant approval.
