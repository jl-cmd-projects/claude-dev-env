# Workstation pressure after partial relief

The operator asked for a short PowerShell command and a CPU and memory verdict. Stopping an idle service freed memory. The live support agent suggested leaving the workers running or closing desktop apps if the workstation still felt sluggish. The operator had to tell it to keep going. The subsequent investigation reported 25.5 GiB in kernel pools, including 11.3 GiB associated with file objects after three jobs finished. The process-level snapshots alone missed that distinction. The driver and a lasting fix remained open. The original turn failed to deliver unassisted.

The separate merge and CI leads also ended with deliverables outstanding in the supervision transcript. A scope correction and a reminder about an earlier approval were visible as well. Those events support their respective evaluations. They do not establish that a worker spent a sustained stretch on an irrelevant side issue. The supervision and pressure exchanges were readable. This sample does not cover all of the operator's estimated eight native worker histories.

## How the replay differs from the live thread

The [frozen protocol](pressure_protocol.md) reconstructs the conversation through the operator's last measurements. The historical assistant reply being predicted, its nudge and subsequent measurements were withheld. The study scaled telemetry, introduced a broken archive viewer, and gave hosted subjects direct access to a read-only PowerShell replay. In the field exchange the operator pasted Windows command output. The participants were fresh sessions with reconstructed history. The study did not duplicate that agent's unobserved reasoning, its native host, operator latency, or hours of a live shift.

The workstation with stock counters retained about 19.1 GiB in kernel pools, including 8.5 GiB in file objects, after four jobs finished. The other workstation's dated captures showed those allocations falling to 3.9 and 1.05 GiB. Inspecting the underlying semicolon-delimited CSV was a valid way to answer despite the viewer fault. The two cases shared the same visible opening files. A CPU reading, free-RAM reading, or success message alone did not establish either conclusion.

Six matched pairs compared the pinned instructions with [the candidate paragraph](pressure_intervention.txt). The study used eight GPT-6.2 Sol High and four GPT-6.1 Sol High sessions. Each pair shared its prompt, console, limits, permissions and model. The runner verified the starting workspace hashes. Models and effort come from explicit hosted launch arguments. The platform returned a distinct worker name for each request. Subjects read their instruction text using the study entry point. This tests the text in a hosted session. Production Codex did not load a modified package.

Judges saw each operator-facing reply, its command results and a separate reference for the evolving host. Three fresh GPT-6.2 Sol High judges each graded four opaque packets. Each reply received one primary grade. The evidence checker also compared console receipts to the source frames and parsed the supplied PowerShell without executing it on the operator's PC. The full archive retains command errors, mixed actions, timeouts, and any first-pass failure preceding recovery.

## First replies and same-worker recovery

| Outcome | Baseline | Candidate |
|---|---:|---:|
| Adequate first handoff, primary blind grade | 5/6 | 5/6 |
| GPT-6.2 Sol High adequate first handoffs | 3/4 | 4/4 |
| GPT-6.1 Sol High adequate first handoffs | 2/2 | 1/2 |
| Sustained detours, primary grade | 2 | 0 |
| Sustained detours among those two on independent reread | 0 | — |
| Side calls / mixed calls, primary grade | 6 / 0 | 3 / 3 |
| Side-call shell seconds | 3.08 | 2.02 |
| Median seconds to first useful result | 22.61 | 15.83 |
| Total calls including useful and unsupported calls | 59 | 67 |
| Missed material dependency / false done | 1 / 0 | 0 / 0 |
| Same-worker nudges sent after first pass | 1 | 1 |
| Post-nudge adequate handoff, rescue judge | 1/1 | 1/1 |

Both primary detour grades were GPT-6.2 Sol High baseline runs. One worker spent 190 seconds on a retained-pool case. The primary judge counted a repeated counter sample, a broad file lookup and two checks after the historical tag was visible. The other worker checked the archive when there was only one export and overlooked two new files after jobs completed. It repeated a counter-path listing and a process snapshot, then asked the operator for a new pool snapshot. A second blind reviewer agreed that the second handoff missed available evidence. The reviewer judged the extra checks in both runs sufficiently exploratory or corroborative to withhold the sustained-detour label. Only one of these two workers needed a nudge. No primary judge scored a repeated no-progress attempt. Separate calls can add no decisive evidence without repeating the same attempt.

The nudge introduced no data or authorization, and both incumbents resumed from their original terminal files with the remaining time. The baseline worker then read all three captures and answered with the post-job pool decline. The candidate worker had already reached that diagnosis but had sent the archive command alone despite executing a live CPU and RAM check. The first-pass and second-decision reviewers found the handoff incomplete. The post-nudge judge considered the earlier command sufficient on a broader reading and saw the continuation as a recheck. Both post-nudge handoffs passed human review. The archive preserves the first pass. For the continuation calls the platform returned an empty response body. The recorded request targets, linked start records, distinct subsequent actions and terminal replies attest resumption.

All 12 first-pass PowerShell excerpts parsed and executed successfully on fresh replay consoles. That establishes operability in the test environment. One command inspected historical memory tags and CI status and did not independently remeasure CPU. The command interface itself rejected 10 Bash requests, five in each arm. Two baseline and five candidate commands hit other adapter limits, including ordinary Windows path or query syntax. These failures remain in the trace and do not by themselves establish distraction.

The strict machine check validated two baseline replies and three candidate replies. It referred five more for review because the receipt extractor could not corroborate all tag and pool fields across job transitions. A separate measurement reviewer confirmed reported measurements on all five. They accepted four exact verdicts and objected to one baseline opening sentence that could be read to exclude an active leak. A second reader credited that reply's subsequent qualified wording. The remaining two replies were the primary handoff failures. An exact-tag requirement would unfairly reject a bounded verdict supported by aggregate pool measurements.

The [independent album holdout](manifest_results.md) did not reproduce a sustained detour on the optional component. The production instruction and fresh-reviewer routes remain at their existing versions.

## Replay

Run from this directory with the pinned Git object available, Python 3 and PowerShell. The [complete archive](evidence/pressure-trials.tar.gz) includes visible operator replies, tool output, launch request settings and receipts, blinded grader decisions, the second readers' findings, and both recovery workspaces. The [machine summary](evidence/pressure-summary.json) reports strict validation and per-run grades separately. The archive contains reconstructed telemetry and excludes the private field exchange.

```sh
pressure_dir=$(mktemp -d)
tar -xzf evidence/pressure-trials.tar.gz -C "$pressure_dir"
python -B pressure_proof.py replay "$pressure_dir" > "$pressure_dir/summary.json"
cmp evidence/pressure-summary.json "$pressure_dir/summary.json"
python -B "$pressure_dir/check_commands.py" first
```
