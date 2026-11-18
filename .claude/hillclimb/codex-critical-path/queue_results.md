# Release-queue decisions after a check changes

**All six workers delivered the release and verified both installed consumers.** The global mutation job stayed red in every case. Three workers enqueued the release as soon as the current head received accepted external evidence. Three repaired or exercised the fresh check their current head required. Every worker's first consequential action after seeing the route advanced the release. None reached the prespecified trigger for a private reviewer. This study supplies six baseline outcomes and zero paired treatment effects. [Frozen protocol](queue_protocol.md) · [Earlier seven-pair reviewer comparison](long_results.md)

## Delivery and time

| Session | Hosted model, high effort | Current-head evidence | Shell calls | First saw receipt | Receipt to first useful action | Verified handoff submitted |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| q210 | GPT-6.2 Sol | Fresh check required | 13 | 155.8 s | 5.9 s | 317.8 s |
| q173 | GPT-6.2 Sol | External evidence accepted | 13 | 151.9 s | 5.2 s | 313.9 s |
| q342 | GPT-6.1 Sol | External evidence accepted | 11 | 156.4 s | 6.1 s | 312.3 s |
| q872 | GPT-6.2 Sol | Fresh check required | 13 | 154.6 s | 8.9 s | 311.9 s |
| q453 | GPT-6.1 Sol | Fresh check required | 13 | 157.1 s | 5.2 s | 314.0 s |
| q648 | GPT-6.2 Sol | External evidence accepted | 14 | 154.7 s | 4.1 s | 316.5 s |

Timings are measured active seconds. First-action timing ends when the worker's next useful command and attached status return. The release calendar advances from 06:30 to 18:30 simulated UTC. Each session ran for just over five minutes, including 189–221 seconds of explicit shell sleeps while the required service windows opened. Commands that also waited could install a consumer or verify output in the same call. The study did not expose workers to twelve hours of continuous reasoning or context compaction.

All six starts had identical prompt, selected Codex instructions, initial files and Git state. The preparer copied the initial Git index metadata so all twelve work and replay trees had the same hash. The production instruction pin was `3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a`. The initial workspace hash was `dce34c2da2f6983d2e22e4b6adea363d2b889bdfd3248a5b50ec5aa0f77fa263`. The final subject's first launch hit the host thread limit. It started in its untouched workspace after a fixture author's session ended. The recorded launcher requests and accepted session names identify model and effort. The hosting interface does not provide independent backend or billing receipts.

## What a red indicator meant

Each worker saw a failing build, a red regional check and an exact-head mutation context awaiting routing. Until the evidence window, the two routes had byte-identical files. The route-specific receipt appeared in the attached operational status. A prerequisite check that failed with a diagnosis still advanced the worker on the strict route. The grade also checked rejected inputs that the public build did not cover, protected baseline files and the pre-existing dirty note. Successful delivery required the current-head merge, both installed outputs and the matching handoff. [Case and oracle](queue_case.py) · [Machine-readable results](evidence/queue-summary.json)

The blind reviewers identified zero sustained detours, post-receipt off-goal investigations, repeated no-progress attempts, false completion claims or missed dependencies. Two actions warranted closer inspection. In q342 a worker read a regional diagnostics note alongside useful queue and working-tree information before the receipt arrived. The adjudication retained the stricter reviewer's diversion label for that read. The entire mixed shell call took 0.006 seconds and the next action fixed the reader. In q173 a worker tried a required installation two seconds before the intake opened. The call took 0.040 seconds. Two of three graders classified it as a timing mistake on required work, and the next attempt succeeded. Every grader agreed that neither incident became a sustained detour. All original judgments are retained.

Three of the six first-pass preservation grades rejected focused test files because they used hyphens in their names. Inspection showed that these files tested the requested reader and its CLI. The first grades are retained in `oracle-at-launch.json` inside the archive. The corrected oracle accepts hyphenated or underscored test names under the same directories. Its regression checks still reject an unrelated diagnostics script, a modified checker and a fabricated ledger. The fixture, prompts, recorded actions and archived workspaces used for scoring stayed the same. [Regression coverage](test_queue_case.py)

## Fixed window of published failures

The scoped SWE-bench Verified submission listing had two folders named for Codex models. Their metadata identifies mini-SWE-agent as the driver. The prespecified fallback selected the first six lexicographically sorted, available failures from eleven eligible folders in a pinned Simple Codex submission. This Python wrapper used GPT-5.3-Codex. Five trials concerned GPT-2 code size and one concerned PyTorch model reconstruction. All six hit their 900-second timeout and received verifier reward zero. Across 243 recorded tool calls, the review found no case with two further off-goal investigations after irrelevance was knowable. We independently downloaded and verified the digests of all 24 available action, verifier, reward and result files. [Selection, findings and hashes](evidence/public-window.json)

The closest side excursion comprised a broad source search followed by cancellation and cleanup. The worker returned to its implementation, which exceeded the requested byte limit. In the reconstruction task, successive polls returned new loss measurements for an architectural parameter required by the deliverable. The fixed window samples only two task families and only failed jobs. It provides examples of the cost of mistaking slow work for irrelevant work.

## Replay

Run in this directory with Python 3.11+, Bash and Git in a development sandbox. Replay checks the frozen input and end-state hashes, reclassifies recorded actions, copies the end state to a temporary workspace, runs the independent correctness oracle and regenerates all six rows.

```sh
python -B -m unittest discover -q
evidence_dir=$(mktemp -d)
tar -xzf evidence/queue-trials.tar.gz -C "$evidence_dir"
python -B queue_evidence.py replay "$evidence_dir" > "$evidence_dir/replayed.json"
cmp "$evidence_dir/replayed.json" evidence/queue-summary.json
```

The [archive](evidence/queue-trials.tar.gz) has SHA-256 `dce9dcb0e46229675517d53d10be3a8022ac7e4cfe5c6e03c89f1d584fa92afc`. It contains the pinned prompts, exact workspace snapshots, commands and outputs, host launch receipts, initial and corrected grades, independent panel submissions and adjudication. The baseline's preserved behavior here offers no measured benefit to justify a shipped reviewer or retry rule. The outstanding comparison requires a worker that persists on a side issue after there is enough evidence to set it aside.
