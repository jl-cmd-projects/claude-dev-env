# Can a conditional reviewer bring a worker back to the operator's task?

Eight matched cloud continuations tested whether a fresh reviewer helped an already-working Codex agent deliver the requested result. Six pairs received the same simulated change in priorities; two continued with the original request and no operator intervention. A ninth worker finished the unchanged-goal held-out task before a review was eligible. All 17 produced the requested files. In each pair both arms agreed on the independent artifact checks.

## Runner correction and historical impact

The original runner consulted the hidden correctness oracle when all expected artifact paths existed, and accepted a review receipt whose checkpoint digest was missing. Those were faults in the evaluation machinery. The corrected runner nominates from information visible to the worker and rejects missing or mismatched digests before displaying advice or starting the continuation. Historical replay still uses the byte-pinned original trigger.

On the downloaded original archive, 13 decisions across all nine prefixes were eligible for examination. The original code consulted the oracle twice, both in the unpaired reserve. Forcing either hidden answer changed zero nominations. The corrected visible-only policy matched all 13 archived decisions. All eight consumed receipts carried the correct checkpoint digest, the source request matched the role plus the checkpoint bytes, and the consumed advice matched the reviewer response. The behavioral totals above therefore stand, while the original runner was unsuitable for reuse. [Per-decision and receipt audit](evidence/pivot-impact.json)

Run `python -B pivot_impact_audit.py "$study_dir"` on the extracted original archive to reproduce the audit.

## Why this case

In the November 18 supervision transcript the operator asked for named merges and resource-efficient CI. During the shift the supervisor proposed investigating watcher frequency. At 12:44 UTC the operator intervened and asked it to pick up ended turns with unfinished work. The next messages identified an undelivered PR fix and a missing Windows CI profile and reported both leads resumed. Another exchange at 14:54 shows the operator had to continue a pressure investigation after an interim memory improvement. These are observed nudges. The available messages establish neither a count of off-goal tool calls nor a successful final deployment in the field.

The executable reconstruction substitutes a validated export and a measured CI profile for the live deliverables. It includes an unfinished timing probe, one already-accepted job, and a locally detached dispatch lease in half the desk pairs. The reserve uses the operator's requirement for next-start memory tracking. Each worker has to produce a command, a saved capture and a usable runbook. Verification executes each capture on a supplied launch and two unseen inputs. Everything ran in temporary cloud checkouts.

## Method and interpretation

GPT-6.2 Sol High handled five of the eight pairs and the unpaired trajectory. GPT-6.1 Sol High handled three pairs. Eight platform full-history forks preserved the parent conversations before either arm saw advice. Original task, workspace hashes, permissions, launch selection and 360-second active budget matched within each pair. A new GPT-6.2 Sol High reader saw the current task, explicit priority changes if any, the worker's own observed actions and the artifact state. It could issue a short redirect or pass. The platform returned worker identities and accepted model/effort selectors; the receipts contain no independent backend model attestation. The active budget charges review time, and the summary reports host routing time separately.

Only candidate arms at an eligible checkpoint opened a review. All eight paired checkpoints were eligible. Two reviewers passed silently; six sent advice. One held-out worker finished in four workspace calls and never triggered review. This measured rule selects unresolved inspections, which can occur during legitimate work. A reviewer observing such an inspection cannot establish a worker has gone astray. The six simulated priority changes test response to an update. Only the separate unchanged-goal trajectories can speak to recovery without that update.

The four strict desk misses occurred in two GPT-6.1 Sol High pairs. Each arm appended handoff progress to the existing operator note and retained its contents. The frozen oracle required byte preservation even though the original user asked to keep the shift handoff current. The strict counts below retain those failures. The product and receipt checks passed and the accepted job remained intact in every desk run. All six continuations with a detached lease made the required repair. All five capture implementations passed all three executions, including on unseen inputs.

## Delivery, diversions and cost

| Frozen cohort | Matched pairs | Products delivered, baseline / review | Strict passes, baseline / review | Median seconds through first useful action, baseline / review |
|---|---:|---:|---:|---:|
| Same operator update in both arms | 6 | 6/6 · 6/6 | 4/6 · 4/6 | 4.13 · 15.02 |
| Same original task, no new user message | 2 | 2/2 · 2/2 | 2/2 · 2/2 | 7.09 · 11.15 |
| Unchanged-goal reserve completed before eligibility | 0 | 1/1 · no reviewed arm | 1/1 · no reviewed arm | completed before a checkpoint |

Two independent blinded readers graded every outcome. They agreed that all 17 workers verified the requested deliverable and that none needed another user turn. Each reader found zero sustained detours, wholly irrelevant calls, repeated no-progress actions, false redirections, false completion claims or missed prerequisites. The 16 paired continuations issued 28 post-checkpoint workspace calls per arm. The common prefix and the four workspace calls of the unpaired reserve are recorded separately. Commands frequently batched multiple operations, so an entirely relevant call can still contain incidental work or a failed lookup.

The eight reviewer sessions consumed 81.32 active seconds. Relative to their paired baseline, review arms took a median 8.15 seconds longer to finish, including the common prefix and reviewer time. Six pairs took longer with review. The other two finished 0.99 and 1.42 seconds faster. Both held-out pairs, and the separate held-out worker that finished before review, already produced capture programs that passed on the two unseen launches.

Both readers initially took “first consequential action” to mean the first mutation in 15 packets. The timing validator rejected those indices. The same blind readers reexamined the indices with a useful prerequisite inspection counted as consequential. Each changed that index only. Original and revised grades are archived. The two final scores agree on every non-prose field.

**Shipping decision.** The fresh reader prevented zero additional nudges and added time on most pairs. These reconstructed tasks did not produce a baseline sustained diversion, so the experiment cannot estimate whether a reviewer rescues a worker that is already stuck. This track made no production change. Its source merge, release, installation and activation counts are all zero. The remaining evidence gap is a cloud-readable worker history from before a real nudge that shows repeated irrelevant actions while the requested deliverable remained unfinished and an authorized next action was available.

## Replay

Run from this directory with Python 3 and the pinned commit available in the Git checkout. The archive includes the launch ledger, actual command traces and checkout contents, reviewer receipts, both independent assessments and the sealed panel mapping. The archive keeps the synthetic checkout Git directories because their bytes and modes are part of the recorded workspace digest. No credentials or live workstation access are needed.

```sh
study_dir=$(mktemp -d)
tar -xpzf evidence/pivot-trials.tar.gz -C "$study_dir"
python -B pivot_proof.py replay "$study_dir" > "$study_dir/summary.json"
cmp evidence/pivot-summary.json "$study_dir/summary.json"
```

[Priority-change protocol](pivot_protocol.md) · [Unchanged-goal protocol](pivot_steady_protocol.md) · [Results by model, case and worker](evidence/pivot-summary.json) · [Replay archive](evidence/pivot-trials.tar.gz)
