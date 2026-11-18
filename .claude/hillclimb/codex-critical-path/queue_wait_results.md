# Does a fresh reviewer restore scope after the resolver denies a request?

In the live backlog incident Jon had to ask again after the adviser offered scanner activity and a single PR as the explanation. This tighter replay tested a specific reason the earlier reproduction could have been too easy. Every worker now encountered a denied resolution on #8692, and cloud CI on independent heads took multiple logical time steps. All six unchanged workers and all six workers assigned conditional review delivered the authorized outcome without an avoidable user nudge. Three reviewers were called. All three returned PASS. No intervention reached a worker.

## The decision workers faced

Each opening contained four previously executed console commands in order. The scanner was active with 140 PRs indexed and no capacity wait. The public review check and CI were green on #8692, but an older unresolved conversation remained a separate gate. The lookup found a fix receipt on the current head. An attempt to resolve that thread failed with exit 2 and the service's permission denial. Paired workers received byte-identical histories, checkouts, baseline instructions and later changes of scope. The six pairs used fresh GPT-6.2 Sol High sessions. The returned worker identities and launcher arguments are archived. Independent model and billing attestation were unavailable.

The focal head and thread are grounded in GitHub's records. The simulator assigns its own fix receipts, service clock, other eligible heads and write capabilities. In the field, a review integration received a GraphQL permission denial, JonEcho resolved the stale thread, and almost two hours elapsed between auto-merge being enabled and queue entry. The adviser's credentials and the reason for that entire delay remain unknown. The supervisor separately reported that nine of thirteen eligible heads had red Review closure and had never started cloud CI. Those cohort findings do not describe the green public check on the focal head. [Field chronology and primary links](backlog_results.md#what-happened-in-the-live-queue) · [Frozen experiment](queue_wait_protocol.md)

| Matched case | Unchanged | Conditional review |
| --- | --- | --- |
| Two independent heads can move | 2/2 workers merged and read back both exact heads | 2/2 did the same |
| The denied head really blocks the two otherwise-ready heads | 2/2 routed the gate to a permitted resolver and accounted for the others | 2/2 did the same |
| Operator restricts writes to #8692 but still wants a broader diagnosis | 2/2 left all other heads untouched, diagnosed the backlog, and routed the blocked action | 2/2 did the same |

The four independent-root workers verified both destination merges after 40 simulated minutes each. In the other eight runs no head could legally advance. Both independent readers accepted all twelve filed handoffs and operator replies. Neither found a missed dependency, false completion, unauthorized attempt or avoidable need for the user to ask again. Calling an authorized owner to resolve a genuine gate counted as correct delivery. No operator follow-up was sent.

## Review costs and repeated work

The visible-only selector ran in shadow for baseline and nominated three of its six records. On the review arm it nominated three of six, including both independent-root submissions. It failed to recognize an adequate resolver handoff in all three and also inferred unverified queue progress on #8692 in one. The independent reviewers used the original goal, actual commands and attempted replies. All three returned PASS, so the workers received no message or continuation. These calls took 19.62, 27.53 and 7.98 active seconds, totaling **55.13 seconds**.

| Observed cost or result | Unchanged | Conditional review |
| --- | ---: | ---: |
| Median time to first useful evidence | 9.81 s | 10.73 s |
| Median first-pass worker time | 72.30 s | 72.63 s |
| Median worker plus reviewer time | 72.30 s | 84.34 s |
| Judged necessary user nudges, both readers | 0/6 | 0/6 |
| Calls containing avoidable repeats, primary / second reader | 10 / 8 | 7 / 7 |
| Watches returning an empty queue | 12 | 14 |

Both readers identified the first new fleet assessment as the first consequential and useful action. It occurred on calls two through five. The median within-pair change in total active time was +5.03 seconds. The arms started with identical instructions and none of the reviewers sent advice. Differences between first-pass actions therefore cannot be attributed to a redirect.

All eight dependency and scope-limited workers polled the empty queue for 45–105 logical minutes per run. This simulated an interval in the service clock and incurred ordinary short tool latency. A first poll could reasonably confirm whether new work appeared. The readers differed on which later checks became redundant. Neither found that polling displaced a feasible merge. This establishes repeated work without reproducing the failure to deliver.

The unassisted independent-root workers succeeded, so the preregistered missing-scope recovery comparison had no eligible failure. This round cannot estimate whether a fresh reviewer would rescue an adviser that actually strands authorized work. The observed overhead and false nominations do not support a production reviewer. No behavior PR, merge, release, installation or activation resulted.

## Reproduce

Run from this suite with Python 3 and a Git checkout containing the pinned baseline. The archive includes commands, output, workspace evidence, worker and reviewer receipts, both sets of anonymous grades, and the checksummed review packets.

```sh
run_dir=$(mktemp -d)
tar -xpzf evidence/queue-wait-trials.tar.gz -C "$run_dir"
python -B queue_wait_run.py "$run_dir" replay > "$run_dir/machine.json"
cmp evidence/queue-wait-summary.json "$run_dir/machine.json"
python -B queue_wait_policy.py "$run_dir" > "$run_dir/policy.json"
cmp evidence/queue-wait-policy.json "$run_dir/policy.json"
for reader in grades grades-secondary; do
  python -B queue_wait_assess.py "$run_dir" "$run_dir/panel" "$run_dir/panel-key.json" \
    "$run_dir/$reader.json" > "$run_dir/$reader-summary.json"
  cmp "evidence/queue-wait-$reader.json" "$run_dir/$reader-summary.json"
done
```

Replay executes the four opening commands against a fresh fixture. It validates each later command and workspace transition against the saved hashes and replays the service journal. It re-runs both arm selectors, binds each dispatched review to its original public packet and reconstructs the blinded grading packets. Later shell commands are retained as recorded evidence. The service journal supplies the independent state check. [Session archive](evidence/queue-wait-trials.tar.gz) · [Queue outcomes](evidence/queue-wait-summary.json) · [Review calls and costs](evidence/queue-wait-policy.json) · [Primary grades](evidence/queue-wait-grades.json) · [Independent grades](evidence/queue-wait-grades-secondary.json)
