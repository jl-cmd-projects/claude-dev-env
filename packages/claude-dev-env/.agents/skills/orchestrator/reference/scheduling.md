# Use an optional owned wake

Ordinary orchestration and manual refresh run without a scheduler.
Use the current runtime's supported automation tool only when the request authorizes a later wake.
Record its owning run, schedule ID, prompt, and next event in the run record.
Reuse an existing owned schedule when the runtime supports it.
Do not substitute another scheduling mechanism when the runtime prescribes one.

## Existing one-shot gate adapter

Use this adapter only when a supported one-shot wake and the existing gate are part of the run.
Resolve `scripts/status_gate.py` relative to the installed orchestrator skill directory.
Pass this run's explicit absolute `--status-file` path on every command.
Keep `--run-slug` consistent and include the stable run locator in the wake prompt.
An unscoped default path can collide with another root.

The gate owns only optional wake state. The selected task authority owns task state.
Keep the gate implementation and runtime hook policy intact.
This skill does not install or enable hooks.

```text
python <status_gate.py> set --status active --run-slug <run-id> --status-file <path>
python <status_gate.py> begin-firing --run-slug <run-id> --status-file <path>
python <status_gate.py> should-reschedule --run-slug <run-id> --status-file <path>
python <status_gate.py> claim-rearm --run-slug <run-id> --status-file <path>
python <status_gate.py> release-rearm --run-slug <run-id> --status-file <path>
python <status_gate.py> set --status done --run-slug <run-id> --status-file <path>
```

| Command | Exit 0 | Exit 1 |
|---|---|---|
| `set` | State written. Reasserting active preserves the pending latch. Done clears it. | Inspect the command error. |
| `begin-firing` | Active run's latch cleared. | Missing, invalid, or inactive state. End this gate firing. |
| `should-reschedule` | Active with an available slot. Read-only. | End this re-arm attempt. |
| `claim-rearm` | Pending slot recorded after successful creation. | Cancel only the wake just created and end this re-arm attempt. |
| `release-rearm` | Pending latch cleared for recovery. | Missing, invalid, or inactive state. End latch recovery. |

For argument errors or other nonzero exits, inspect the error and preserve running work.
A denied re-arm ends only that attempt. It neither completes goals nor pauses executors.
A missing or inactive gate ends the scheduled gate firing; recover unresolved work through the ordinary entrypoint.

## Preserve one pending wake

Only the current root owner operates its gate. The gate does not arbitrate competing parent ownership.
Register applicable scheduling work in the task authority before changing a wake.
At a verified firing, run `begin-firing` for the recorded gate before attempting a new one-shot wake.
A manual refresh leaves an outstanding wake's latch intact.

For a re-arm, run `should-reschedule` first. Exit 1 creates no wake.
After exit 0, create one supported, non-recurring delayed wake, then run `claim-rearm` immediately.
Create before claiming because the existing Claude gate hook checks the pending latch before creation.
Record the returned schedule ID. If claim fails, cancel only that newly created ID.
If creation fails, leave the slot unclaimed and continue independent work.
If creation has an unknown outcome, inspect owned schedule state before retrying.
If cancellation or inspection is unavailable, record the uncertainty and create no replacement wake.

Use `release-rearm` only after checking whether the recorded wake still exists.
Keep the existing latch while an owned wake remains pending or its state is unknown.
Cancel a schedule only by its recorded ID or an exact run-specific locator match.
Never cancel every prompt containing `/orchestrator-refresh`; other roots may own those prompts.

When all run completion predicates hold, set this gate to done and retire only this run's owned wake.
An unavailable cancellation tool leaves a recorded unresolved wake for follow-up.
Runtime automation policies take precedence over this optional one-shot adapter.
