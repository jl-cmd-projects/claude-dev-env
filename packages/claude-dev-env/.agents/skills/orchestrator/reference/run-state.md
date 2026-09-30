# Keep a recoverable run

## Discover every active root

Use the supplied project directory as the discovery root, even when workers use separate worktrees.
The default registry is `<project-dir>/.orchestrator/active-runs/`.
Each root owns one `<run-id>.md` locator there and one stable run directory.
Choose a unique run ID before writing. Reuse an existing ID only after confirming ownership.
The default run record is `<project-dir>/docs/plans/<run-id>/run.md`.
Keep private run records out of published source and commits.

Each locator records these fields:

| Field | Meaning |
|---|---|
| `run_id` | Stable ID shared by the locator and run record. |
| `project_dir` | Absolute discovery root supplied for this project. |
| `run_record` | Absolute path to the durable run record. |
| `task_authority` | Tool namespace and list ID, or the existing ledger's absolute path and adapter. |
| `root_owner` | Current parent session identity and available contact route. |
| `updated_at` | Timestamp of the latest locator change. |

The directory is the active-root registry. Roots write separate locator files.
Preserve other roots' entries. A shared summary index, when present, is a derived view.
An alternate home requires an exact pointer in loaded project instructions or verified runtime startup data.
Before delegation or waiting, confirm that the supplied project directory and loaded instructions lead to this run.
A cold session also needs to load the recovery guidance.
Verify a loader pointer in an automatically read project instruction file or an already configured startup mechanism.
That pointer names the installed orchestrator entrypoint and the project-relative registry directory.
Establish a missing pointer only within authorized scope. Keep hook settings and manual invocation policy unchanged.
If no pointer can be established, record that cold-start loading is unverified and provide the explicit resume locator.
A pstack latest-checkpoint pointer can be overwritten by another root. Keep each stable locator independently.

## Choose one task authority

Use the exposed host task tool and record its namespace and persistent list ID.
Verify whether a replacement session can reopen that list.
Task status, ownership, and dependencies live only in this authority.
Record the parent's coordination task there alongside implementation, review, and delivery tasks.

When host task tools are absent, reuse the configured file-ledger adapter.
This package provides `scripts/grok_run_ledger.py`; the installed shared copy is `.agents/scripts/grok_run_ledger.py`.
Locate that file in the current installation before selecting it.
It exposes only the Python `GrokRunLedger` API.
Use its existing supported caller or Python API and preserve its schema and transition rules.
Its tests are `scripts/test_grok_run_ledger.py` in the package.
The API covers task IDs, dependencies, ownership, review evidence, and completion.
Keep unsupported descriptive fields in the run record keyed by task ID.
If no callable tool or working adapter exists, report that limit and stop new tracked dispatch.

When a task store is transient, keep timestamped recovery snapshots of its records.
Label each snapshot as historical and name the authority it copied.
After loss, reconcile a snapshot with live evidence before importing into one replacement authority.
Record the migration and retire the prior store as writable authority only after ownership is settled.

## Preserve intent and follow-up metadata

The run record holds durable intent and pointers, separate from changing task status.
Keep it short enough to reload. Move assignments and long evidence into linked files.

| Record | Required content |
|---|---|
| Run | Run ID, discovery root, parent owner, task authority, current mode, checkpoint time. |
| Each goal | Goal ID, user's source wording and message locator, constraints, priority, acceptance conditions, task IDs, goal state, accepted evidence. |
| Each task's metadata | Task ID, goal IDs, assignment path, next action, waiting condition or next check, artifact links. Read status and owner from the authority. |
| Parent follow-up | Parent task ID, goals still owed, integration or verification step, next action, waiting condition. |
| Worker | Task ID, executor identity, contact route, owned paths, partial output locator, latest liveness observation and timestamp. |
| Decision or approval | Source message, exact approved scope, pending action, granted or pending state, constraints, expiry or revocation when given. |
| Recovery | Last checked artifacts, open uncertainty, snapshot locator, task-store recovery method, next permissible action. |
| Optional wake | Owning run ID, runtime, schedule ID, prompt locator, next event, and gate path when used. |

Derive the short follow list from the authority joined to this metadata by task ID.
Keep its observation time visible. Refresh it on messages, decisions, worker changes, and completion.
Preserve unrelated goals when a user asks a question, changes one task, or completes one goal.
Goal completion needs evidence for the full outcome, including any authorized delivery.

Checkpoint after each material change and before waiting, ending with open work, or known compaction.
Read owned shared files before updating them and verify the saved result.
Save intent before dispatch so a loss between dispatch and registration cannot hide a worker.
Store stable project preferences only through the authorized memory workflow.
Open tasks belong in the selected task authority. Private reasoning and credentials belong in neither record.

## Task seeds

Register each applicable item through the selected task authority. Reuse existing IDs on refresh.
Give skipped items a reason. Complete items only with evidence.

1. Establish the run locator, task authority, and durable user goals.
2. Track the parent's follow-up and every scoped task with ownership and dependencies.
3. Execute the permitted next actions and inspect returned evidence.
4. Reconcile goals, approvals, worker ownership, and recovery state before waiting or completion.
