# Can Codex catch an incomplete handoff before the operator intervenes?

**An explicit warning about an observable discrepancy improved delivery in the workstation replay. The portable instruction failed to reproduce the improvement.** A fresh reviewer recovered one more handoff than the warning alone, and added time on a correctly limited reply. These runs support a diagnosis of incomplete handoffs. They did not reproduce sustained diversion after the checkpoint.

The [earlier pressure study](pressure_results.md) recorded two operator handoffs that needed further work. One worker left a pool question with the operator even though newer captures were available. The other measured CPU and RAM, then sent only the archive command. Each new pressure session received the original operator exchange, the exact sequence of visible console calls and output, the same terminal workspace, and the pending reply. A solver could send the draft unchanged. It did not see any later nudge, recovery answer, grader labels or private reasoning. These fresh sessions reconstructed the same worker's evidence. They could not rewind its hidden context. Pstack separately reported reproducing all twelve inputs for the first comparison byte for byte at c3cebea. Solvers ran with explicit GPT-6.2 Sol High or GPT-6.1 Sol High launch arguments. The platform returned unique worker names and did not return separate backend attestations for model or effort.

## Delivery and cost

| Comparison and arm | Independent first handoffs accepted | Nudge judged necessary | Missed dependencies | Sustained detours after cutoff | Median seconds from checkpoint |
|---|---:|---:|---:|---:|---:|
| General final check, baseline | 3/6 | 3 | 1 | 0 | 15.7 |
| General final check, added text | 2/6 | 4 | 1 | 0 | 18.6 |
| Targeted discrepancy, unchanged | 2/6 | 4 | 2 | 0 | 12.6 |
| Targeted discrepancy, warning alone | 5/6 | 1 | 0 | 0 | 22.2 |
| Targeted discrepancy, warning and conditional reviewer | 6/6 | 0 | 0 | 0 | 30.1 |
| Portable instruction, pressure baseline | 3/4 | 1 | 0 | 0 | 21.3 |
| Portable instruction, pressure candidate | 2/4 | 2 | 1 | 0 | 25.1 |
| Portable instruction, independent CI baseline | 6/6 | 0 | 0 | 0 | 19.1 |
| Portable instruction, independent CI candidate | 6/6 | 0 | 0 | 0 | 21.0 |

These are 50 new first-dispatch decisions in three separately frozen comparisons plus five fresh reviewer calls. Repetitions share historical checkpoints, so they do not represent 50 independent field incidents. The operator did not receive an experimental nudge in these comparisons. A nudge judged necessary is an unresolved, available action at first reply. The earlier field nudge and the two subsequently measured same-worker rescues are distinct observations.

**General check.** Two incomplete decisions were repeated twice each and two adequate controls were retained. On the archive-only handoff all four Sol 6.1 workers sent the original incomplete draft. One Sol 6.2 candidate retrieved the missing captures and lost the working live CPU command when updating the answer. Both controls passed in both arms. The [preregistration](draft_protocol.md), [candidate](draft_intervention.txt), [per-run grades](evidence/draft-summary.json) and [archived workspaces](evidence/draft-trials.tar.gz) preserve the comparison.

**Targeted check.** The [frozen study rule](signal_rule.py) flags code without a CPU measurement after the operator asked for both CPU and memory and the worker ran a CPU query. Its other branch flags language about limited observations. It selected three of the twelve historical drafts, including an adequate handoff. In six matched triplets, Sol 6.1 delivered 1/3 unchanged, 3/3 with the warning and 3/3 with review. Sol 6.2 delivered 1/3, 2/3 and 3/3. Each of the five triggered review trials received its own fresh GPT-6.2 Sol High reader. Reviewers found the later captures or the live command in the four incomplete starts. The fifth said PASS. The readers used 67.2 active seconds and five console calls in aggregate. Those costs are included above. On the adequate handoff that triggered the rule, the unchanged answer took 19.6 seconds, the warning 67.0 seconds, and the warning plus reviewer 41.6 seconds. The limited sample supplies one comparison for that control. The unflagged control never launched a reviewer. [Frozen protocol](signal_protocol.md) · [Per-run time and grades](evidence/signal-summary.json) · [Review advice, console actions and workspaces](evidence/signal-trials.tar.gz)

**Portable instruction and independent holdout.** The [candidate](dispatch_candidate.txt) asks for a working command that covers each requested measurement and a recheck of a source that could have changed. Workers received no case-specific warning or review. Its development result was 2/4 from 3/4. The two independent readers differed in strictness on two replies from the stale-archive source. Both replies deferred the pool trend without inspecting later captures. Passing both or failing both brings the arms to a tie. Neither reading establishes an improvement. The independent CI workflow required queue depth, oldest pending wait, a runnable check and a launch decision. A separate fixture author created the cases without the pressure outcomes. One waiting case per model had no current timing data. All twelve workers delivered the correct result or an honest limit, preserved the checkout and supplied a command that ran on both initial and changed inputs. Both Sol models scored 3/3 in each CI arm. Independent readers distinguished conditional threshold language from an instruction to launch an extra runner. [Preregistration](dispatch_protocol.md) · [Pressure grades](evidence/dispatch-pressure-summary.json) · [CI grades and executable oracle](evidence/dispatch-ci-summary.json)

The pressure commands passed PowerShell parsing. All twelve excerpts in the general-check batch ran on a staged console, including one 25-second sleep sequence that first hit the adapter's 20-second limit and succeeded with a longer verification window. In the targeted batch 17/18 entire excerpts ran. The remaining Sol 6.2 warning-only reply combined a valid live-counter check with a temporary PoolMon output file. The read-only adapter refused that file operation. The exact live-counter portion ran independently. Its full command is unverified on Windows. All eight portable pressure excerpts ran in the staged console. Operator-facing runnable words, measured signal coverage and live Windows activation remain separate facts.

## Shipping decision

The pressure warning depends on fixture-specific terms. The portable replacement did not reduce incomplete handoffs. Neither portable arm exhibited a detour on the independent workload. The five extra readers are therefore not warranted as a general Codex rule.

The independently merged completion change already selects the stale-capture closing. Its new phrase matcher returned feedback for that one closing and none for the other eleven original pressure replies, including the archive-only command. The check directly invoked the merged matcher on the exact replies. It did not invoke other Stop gates or establish activation. The packaged Codex instruction hash at that merge equaled the earlier pinned hash. No production PR, release, installation or activation resulted from the present comparison. [Completion change at a300d6e](https://github.com/jl-cmd-projects/claude-dev-env/pull/2453)

## Replay

Use Python 3, Git with the pinned source commits available, and PowerShell from this directory. The published archives preserve receipts and judgments, including cases the graders or command adapter could not settle automatically. Preserve recorded file modes when extracting the CI runner because its executable mode is part of the fixture hash.

```sh
draft_dir=$(mktemp -d)
tar -xpzf evidence/draft-trials.tar.gz -C "$draft_dir"
python -B draft_proof.py replay "$draft_dir" > "$draft_dir/summary.json"
cmp evidence/draft-summary.json "$draft_dir/summary.json"

signal_dir=$(mktemp -d)
tar -xpzf evidence/signal-trials.tar.gz -C "$signal_dir"
python -B signal_proof.py replay "$signal_dir" > "$signal_dir/summary.json"
cmp evidence/signal-summary.json "$signal_dir/summary.json"

for suite in pressure ci
do
  dispatch_dir=$(mktemp -d)
  tar -xpzf "evidence/dispatch-${suite}-trials.tar.gz" -C "$dispatch_dir"
  python -B dispatch_proof.py replay "$suite" "$dispatch_dir" > "$dispatch_dir/summary.json"
  cmp "evidence/dispatch-${suite}-summary.json" "$dispatch_dir/summary.json"
done
```
