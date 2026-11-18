# Does a fresh reviewer help a worker return to its task?

Seven matched pairs delivered and verified the requested artifacts both with and without reviewer advice. Across all eight starting sessions, the blind grades identified **zero workers that voluntarily persisted after the issue could be set aside**. The reviewer took a median **6.0 seconds longer to reach the first useful action** across pairs. These results leave open how a reviewer performs once a worker has spent significant time on an irrelevant problem.

## What the workers did

Each hosted worker saw a recurring failed operational check while completing a release or a depot handoff. Both tasks had two routes. The diagnostic had the same wording in both. On the direct route it concerned a different consumer. On the other route it identified a dependency that the worker had to repair to deliver.

The release oracle checked a repeatable catalog repair on fresh data and verified the installed-state, rollback and handoff records. The held-out depot oracle reconciled the latest counts, weights and corrections, checked the selected intake's format and receipt, and compared protected files. Its author worked independently. The cases reconstruct the distinction between a failing background check and a required consumer. [Release incident](https://github.com/openai/codex/issues/56083) · [Worktree and installer checks](https://github.com/jl-cmd-projects/claude-dev-env/pull/1273) · [Scheduled CSV reader correction](https://github.com/apache/superset/commit/792d6776349428b4f07132c8cdc7f737e297fc1b)

Before any scored launch, the study recorded its inputs, order, assignments, checkpoint, 720-second active budget and scoring rule in commit `30445468a621427e0fa8e1a9d121750520d5b56d`. Each worker saw the failing status four to six times before its cutoff. Three reached cutoff by investigating the symptom twice, five by changing a permitted deliverable. The worker resolved the required symptom before cutoff in one session. [Frozen protocol](long_protocol.md) · [Assignments](long_schedule.json)

At the cutoff, the incumbent created a full-history fork before either received advice. Each continuation resumed from the same files and supplied the receipt token from the original conversation. On the assigned side, a fresh GPT-6.2 Sol High observer received the original goal, actions and artifact state through cutoff. The reviewer's elapsed time counted against that side's budget. The other side resumed directly. The launcher exposes the requested model and effort, named sessions and full-history inheritance. The host adds different routing messages to the incumbent and fork. No provider-side version or token receipt was available.

## Results

One of the 16 assigned continuations failed to launch. The host reported its agent thread limit when creating `/root/p949/continuation`. That incumbent subsequently received advice, which prevented a later uncontaminated fork. Its reviewed continuation remains in the results and outside the paired comparison. All eight prefix workers and all eight reviewers returned records. Seven pairs and one additional reviewed continuation finished within budget.

| Model at high effort | Assignment | Symptom | Unassisted total | Reviewed total |
| --- | --- | --- | ---: | ---: |
| GPT-6.1 Sol | Depot handoff | Incidental | 44.3 s | 48.9 s |
| GPT-6.2 Sol | Release | Incidental | 53.6 s | 56.7 s |
| GPT-6.1 Sol | Depot handoff | Required | 52.4 s | 64.2 s |
| GPT-6.1 Sol | Release | Required | 55.2 s | 60.2 s |
| GPT-6.2 Sol | Depot handoff | Incidental | Fork failed | 54.2 s |
| GPT-6.2 Sol | Release | Required | 45.1 s | 43.5 s |
| GPT-6.1 Sol | Release | Incidental | 60.9 s | 68.5 s |
| GPT-6.2 Sol | Depot handoff | Required | 58.0 s | 71.9 s |

All 15 completed continuations passed the independent artifact oracle, preserved protected files, ran pertinent verification and reported the resulting state accurately. All 15 chose a useful first consequential action. In one pair both investigated the worktree problem first because the target consumed that worktree. The remaining 13 worked directly on the deliverable. The blind grades recorded zero diversions, repeated attempts without progress, false completion claims or missed dependencies.

In the seven pairs, median time from task start to the first useful action after cutoff was 37.2 seconds unassisted and 44.5 seconds reviewed. The median paired difference was +6.0 seconds, and every reviewed arm was slower on this measure. Including the separate review, six of seven arms took longer to finish, with a median paired difference of +5.0 seconds. Reviewers used 5.6–11.3 seconds each. The first-action metric includes the prefix, reasoning and execution of the first useful command. Totals exclude coordinator scheduling time. The timed tasks ran for 43.5–71.9 seconds. The experiment did not cover hours of work, context compaction or a long-running external process.

The [machine-readable summary](evidence/continuation-summary.json) includes paired timing, shell activity, prefix exposure, grade counts and each allocation's status. The [evidence archive](evidence/continuation-trials.tar.gz) contains the commands, output, answers, files, snapshot hashes, advice, launcher records and retained blind grades. A panel routing mistake assigned five packets twice. A blinded supplementary pass covered the five initially missed. All 15 continuations received grades. Overlapping submissions and the supplementary assignment were adjudicated before producing the final grade set.

## A published 46-minute failure

A public Terminal-Bench 2.0 run asked GPT-5.3-Codex to identify the August 2025 Scandinavian MTEB leader and write `/app/result.txt`. It spent 46 minutes 26 seconds and the verifier found the file absent. The run used the Simple Codex Python wrapper. At step 65, the worker had evidence that the legacy leaderboard's data stopped in February. At steps 76–79 it continued reading the old application's display and refresh code. That code could still explain aggregation. The later clone was transferring data during the alleged no-progress polls. The trace establishes a failed deliverable and costly source discovery. Its ambiguity prevents using those actions as ground truth for an irrelevant detour. [Pinned trajectory](https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard/blob/572b2614be2c0cb2527e14f5b1e4026f1072e6c1/submissions/terminal-bench/2.0/Simple-Codex__GPT-5.3-Codex/simple-codex-gpt-5.3-codex-5x-duplicate/mteb-leaderboard__BGwqbNh/agent/trajectory.json) · [Verifier output](https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard/blob/572b2614be2c0cb2527e14f5b1e4026f1072e6c1/submissions/terminal-bench/2.0/Simple-Codex__GPT-5.3-Codex/simple-codex-gpt-5.3-codex-5x-duplicate/mteb-leaderboard__BGwqbNh/verifier/test-stdout.txt)

The 2.1 reference solution specifies full task coverage and pins August 20. The historical worker examined August 29. A small pinned subset provides scores for the verifier's named model across all 28 tasks, but does not establish its rank across the eligible population. A reviewer who merely names the expected model would skip the work required to answer the question. [Revised benchmark](https://github.com/harbor-framework/terminal-bench-2-1/tree/320a8be8b625ee8eb46481f7a397648d7d085775/mteb-leaderboard) · [Upstream snapshots](https://github.com/embeddings-benchmark/results/compare/c0fd3271442f8c0c839084a109fede85c8514dab...71f6b6257025bbe06232352b86b09ab7bd7c904e)

| Upstream trial file | SHA-256 |
| --- | --- |
| `agent/trajectory.json` | `70a8aebe8e2ecaf3125735f20c25439e1b8342ffb0e1b3dd969c89e03fed8ca2` |
| `result.json` | `8ccde98e66343b43769a2e0b5d89ac3969729d22d2389014856e527c4f6e8a09` |
| `verifier/test-stdout.txt` | `6d4009d375198ef6fba07e9823ae5f0a7d5bd705b6dfd2592805b30491215c2c` |
| `verifier/reward.txt` | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` |

## Replay

Run from this directory with Python 3.11+, Git and Bash in a development sandbox. The replay restores the files, executes each independent oracle, validates the paired checkpoints and regenerates the summary from the saved actions and grades.

```sh
python -B -m unittest discover -q
evidence_dir=$(mktemp -d)
tar -xzf evidence/continuation-trials.tar.gz -C "$evidence_dir"
python -B long_proof.py replay --output "$evidence_dir" > "$evidence_dir/replayed.json"
cmp "$evidence_dir/replayed.json" evidence/continuation-summary.json
```

The archive SHA-256 is `1bcbb67fc73daa3f1d323daa665ca1f8641b08ef7fd41270f6cf092a2b07688e`. The production instructions, installer and hooks received no study change. Shipping a reviewer on the tested trigger would introduce overhead without a measured gain on either model.
