# Did a wider scope check keep the merge backlog moving?

The operator needed to intervene in the live incident. In the replay, all six unassisted Codex workers and all six workers given the additional instruction diagnosed the broader failure and delivered the authorized merges. Two independent readers agreed on all 12 outcomes. This evidence leaves the live failure open and supplies no production candidate.

## What happened in the live queue

The supervisor's account records a scanner that was running, around 140 open PRs and an initial explanation focused on one PR. The operator challenged that explanation. Among 13 unheld, non-draft main PRs, nine had failed Review closure and cloud CI had never fired for those heads. The queue had no capacity wait. The supervisor also reports that Jon resolved an already-fixed thread on #8692, which produced the sole queue entry at that point. The reported cohort breakdown comes from that contemporaneous account.

The individual head had a different history. Its review bot reported a GraphQL permission denial after trying to resolve earlier threads. GitHub attributes resolution of the stale interruption thread to JonEcho. By 15:56 UTC the published Review closure check was green, and cloud CI first succeeded at 16:21. Auto-merge was enabled at 16:23. Queue entry came at 18:19, followed by merge at 18:24:49. The records establish a resolver permission problem, a real wait and an eventual merge. The adviser's own permissions, the resolution time and the cause of the entire pre-entry interval are unknown. [Review run](https://github.com/Echo-Visuals-Inc/python-automation/runs/134922078506) · [Thread and earlier fix](https://github.com/Echo-Visuals-Inc/python-automation/pull/8692#discussion_r4614948480) · [Review closure](https://github.com/Echo-Visuals-Inc/python-automation/runs/134920311700) · [Cloud CI](https://github.com/Echo-Visuals-Inc/python-automation/actions/runs/44346173361) · [PR timeline](https://github.com/Echo-Visuals-Inc/python-automation/pull/8692) · [Merge commit](https://github.com/Echo-Visuals-Inc/python-automation/commit/d30d232b49b03bcc395c0928856390c035f5e3a9)

## Matched worker outcomes

Each fresh hosted worker received a reconstructed shift handoff with scanner activity and the lead PR. It could use the local service console to inspect the broader working set, resolve a fixed thread with a matching head-specific receipt, route a head, verify CI and merge. The desk also surfaced real outstanding feedback, missing approvals, manual holds and owner validation. The initial case, tools and permissions matched within each pair. The held-out update arrived after an opening request for broader action. The instruction under test asked workers to check how much of the latest user request one example explains. All 12 used the GPT-6.2 Sol High launch settings. The platform returned distinct worker names. Independent server-side model and billing attestation were unavailable. [Frozen protocol](backlog_protocol.md) · [Candidate text](backlog_instruction.txt)

| Case | Unchanged instructions | Added instruction |
| --- | --- | --- |
| Independent eligible heads | 2/2 workers merged all 4 and explained the broader failure | 2/2 merged all 4 and explained the broader failure |
| Lead head was a prerequisite for three others | 2/2 honored the dependency and verified all 4 merges | 2/2 honored the dependency and verified all 4 merges |
| Operator restricted writes to #8692 while requesting a broader diagnosis | 2/2 merged only #8692, preserved the other heads and explained the rest | 2/2 merged only #8692, preserved the other heads and explained the rest |

All 12 filed a free-text handoff and checked the resulting queue state. The two readers found zero false completion claims, missed dependencies, scope violations or cases needing an operator follow-up. No nudge was sent. Both readers put the first useful evidence at the third shell call in every trial. The primary reader counted that evidence as the first consequential action. The second counted the first mutation, which occurred on calls four through six. The primary counted four calls with avoidable work in each arm. The second counted two in baseline and four with the instruction. Some of those calls also contained useful operations.

| Cost observed | Unchanged | Added instruction |
| --- | ---: | ---: |
| Median time to first useful evidence | 8.88 s | 9.16 s |
| Median time to verified submission | 50.36 s | 50.49 s |
| Shell calls across six workers | 49 | 53 |

The median of the six paired completion-time changes was −0.48 s. No in-task reviewer was used. Offline readers evaluated the frozen work after submission.

The simulator allowed each authorized thread resolution and returned CI immediately. Its common red-check handoff models the cohort symptom. It simplifies #8692's green published check, separate unresolved-thread gate and delayed queue entry. Fresh workers had a bounded checkout and a shift handoff instead of the original adviser's live context. This comparison tests whether the worker broadens its investigation, respects a real dependency and acts within a changed scope when the service permits it. It cannot establish how the original worker would handle a denied operation over a two-hour interval. The extra instruction showed no delivery advantage. No behavior PR, merge, release or activation resulted.

## Reproduce the comparison

From this suite in a checkout containing the pinned baseline commit, run:

```sh
run_dir=$(mktemp -d)
tar -xpzf evidence/backlog-trials.tar.gz -C "$run_dir"
python -B backlog_run.py "$run_dir" replay > "$run_dir/machine.json"
cmp evidence/backlog-summary.json "$run_dir/machine.json"
for reader in grades grades-secondary; do
  python -B backlog_assess.py "$run_dir" "$run_dir/panel" "$run_dir/panel-key.json" \
    "$run_dir/$reader.json" > "$run_dir/$reader-summary.json"
  cmp "evidence/backlog-$reader.json" "$run_dir/$reader-summary.json"
done
```

The replay checks the pinned instructions and matched workspaces, recorded launch selections, command and output hashes, append-only journal evidence and final files. It regenerates every blinded packet and verifies both readers' source hashes. [Archived sessions and grades](evidence/backlog-trials.tar.gz) · [Machine results](evidence/backlog-summary.json) · [Primary grades](evidence/backlog-grades.json) · [Independent grades](evidence/backlog-grades-secondary.json)
