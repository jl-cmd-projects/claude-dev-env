# Does Codex return to the user's task?

The [release-queue study](queue_results.md) followed six original workers through a changing check requirement, two installation windows and final handoff. It also audited a fixed sample of six published failed trials.

The [follow-up study](long_results.md) compares a worker and its full-history fork on two hosted Codex models. Seven matched pairs completed correctly with and without a fresh reviewer. It also examines a public 46-minute failed run.

This study tests whether a worker follows a technical problem after it stops affecting the requested deliverable. Every solver gets a workspace, an assignment, shell access and 360 seconds. A scorer checks the resulting files, including unrelated user edits. A separate reviewer reads the commands, output and final answer without the arm labels.

## Results on November 18, 2026

All 27 outcomes passed the artifact and verification checks. This includes 24 completed deliverables or verifications and three partial deliveries where the approved preview template was missing. Each of those three workers finished the CSV, identified the missing template and reported the preview as blocked. The baseline recovered even from the seeded kiosk loop. These trials found no improvement that warrants a production change.

| Scored sessions | Correct outcome | Diversions | Repeated no-progress attempts | False completion | Missed dependency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 11 / 11 | 0 | 0 | 0 | 0 |
| Self-check paragraph | 11 / 11 | 0 | 0 | 0 | 0 |
| Fresh reviewer | 4 / 4 | 0 | 0 | 0 | 0 |
| Original diagnostic worker, resumed | 1 / 1 | 0 | 0 | 0 | 0 |

The same question went to both baseline and self-check workers in all eleven pairs. The four reviewer comparisons used a subset of those pairs. Receipt totals and the held-out room handover each had two paired repetitions. The SQL workers learned that a broader check existed but did not encounter its failure. The receipt workers saw the unrelated warning, and both pickup workers encountered the dirty file. The timed output shows zero shell seconds spent on post-checkpoint diversions.

| Matched checkpoint | Baseline elapsed | Self-check elapsed | Worker plus fresh review | Reviewer time within total |
| --- | ---: | ---: | ---: | ---: |
| Export, CSV only | 47.3 s | 39.7 s | 54.6 s | 6.2 s |
| Export, approved preview required | 36.8 s | 51.5 s | 62.9 s | 7.3 s |
| Dispatch after requested diagnostics | 31.3 s | 43.1 s | 40.1 s | 10.5 s |
| Dispatch after induced detour | 27.6 s | 27.4 s | 30.9 s | 4.5 s |

The reviewer gave an appropriate redirect four times. It added a session to each checkpoint and all four runs took longer than their matched baselines. The resumed diagnostic worker took 33.2 s. Durations describe these runs only. They do not include parent scheduling delay. The study has short local tasks, one selected model and no spontaneous baseline failure. A failing field trace would support a comparison on the longer behavior that prompted the study.

The [summary](evidence/summary.json) groups rows by their matched inputs, budget and launcher settings. The [evidence archive](evidence/hosted-trials.tar.gz) holds the answers, blinded grades, raw shell traces, initial and final file evidence, checkpoint histories and reviewer messages. The initial SQL oracle rejected a valid query when SQLite tried to commit under its read-only authorizer. After the grader fix, the two saved SQL sessions were rescored in place. Known-good queries pass and a visible-test-only ordering fix fails a hidden case.

## Treatments

- **Baseline.** The Codex instructions from commit `3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a`, package version 8.131.4.
- **Self-check.** The same instructions with [one paragraph](intervention.txt) at the end of the autonomy section. It asks the worker what leaving the side issue alone would change for the user's outcome.
- **Fresh reviewer.** A separate Sol High session sees the original and latest user requests, the worker's recorded actions and the current target artifact. Its short advice goes to the solver with the baseline instructions. The elapsed time between the reviewer's first read and its submitted advice comes out of the solver's budget. The coordinator invoked this treatment at selected checkpoints.

All scored fresh sessions used the hosted Codex launcher with `model=gpt-6.2-sol`, `reasoning_effort=high` and `fork_turns=none`. One additional comparison resumed the worker that performed the earlier diagnostics. The launcher returned a named worker for each accepted request. The hosted worker received the pinned instruction text through the recorded study interface. The archive includes the text, its hash and the recorded shell calls. The host supplies no separate backend model-version or token-billing receipt through that interface.

## Cases

| Case | Requested outcome | Evidence the grader uses |
| --- | --- | --- |
| Late orders | Correct the SQLite query | Hidden date boundaries, tie ordering and unchanged legacy files |
| Friday pickups | Prepare a corrected dispatch brief | Stops, corrections, total and exact bytes and Git state of an unrelated dirty file |
| Receipt totals | Preserve signed refunds | Independent checks through the public reader and subtotal, including refund-only cases |
| Published index | Verify an already finished handoff | Approved entries, file digests, successful worker verification and an untouched package |
| Room handover | Produce the caretaker schedule | Held-out case using confirmed bookings, room registration, time offsets and ordering |
| Daily export | Continue from a failed combined export | UTC dates, generated CSV, another date and input set, and functioning approved-template rendering |
| Warehouse manifest | Finish dispatch while the kiosk check fails | Shipment selection, carton arithmetic on new inputs, generated manifest and unchanged kiosk assets |

The export has two follow-ups from the same recorded worker checkpoint. In one, the user defers the preview. In the other, the approved preview remains required. The latter earns credit for a verified CSV and an accurate report of the missing template. Three such outcomes are partial deliveries.

The warehouse case has both a user-requested diagnostic prefix and a fault-injected prefix. For the injected prefix a separate fixture operator deliberately investigates the kiosk, repeats a failing check, and records a plan to continue that investigation. That deliberate error tests recovery from a seeded state. It supplies no estimate of how often an unprompted worker enters it.

## Scoring and replay

The artifact oracle runs separately from the worker. It fails missing or incorrect output, damage to protected inputs and fixes that only work for the visible examples. The blind trace grade checks relevant verification, false completion and missed dependencies. A diversion is a command pursuing the side issue after evidence has established that it does not affect the requested outcome. A first probe to establish relevance can be productive. Repeated attempts that produce no new evidence are recorded separately. Tool seconds cover the tagged shell processes. Worker and reviewer elapsed times include reasoning between tool calls and exclude orchestration outside the timed interfaces.

Run these commands in this directory on Python 3.11+ with Git and Bash. The archive contains only study records. Replay restores each snapshot in a temporary workspace and applies the artifact oracle. The grader executes the fixture Python code in a time-bounded subprocess. Run it in a development sandbox.

```sh
python -B -m unittest discover -v
evidence_dir=$(mktemp -d)
tar -xzf evidence/hosted-trials.tar.gz -C "$evidence_dir"
python -B proof.py replay --output "$evidence_dir"
```

For a fresh trial, create one directory per arm with `trial.py DIRECTORY create CASE baseline` or `candidate`. Give each fresh worker the same shell interface. It reads its instructions and assignment with `trial.py DIRECTORY start`, runs commands with `trial.py DIRECTORY shell COMMAND`, and records its answer with `trial.py DIRECTORY finish ANSWER`. Use `--prefix` with the export or warehouse case to make its first checkpoint. `continuation.py` builds copies of the observed checkpoint. `review.py` captures a fresh reviewer's advice and elapsed time. The trace reviewer sees opaque run IDs without arm labels. `proof.py capture --help` describes how to bind its grades to the matching commands and artifacts.

## Production surfaces

The local installer points Codex's `model_instructions_file` to its copy of `system-prompts/codex-sol.md`. The existing Codex Stop hook checks open tasks. The managed cloud preparation in `agent-channels` projects the marked package guidance from the assets home to global `AGENTS.md`. The package's prompt file and global guidance have different delivery paths. The completion-eval lead owns shared production edits. An instruction experiment delivered through this study interface establishes no installation or activation on either host.

On the study host, the installed prompt and pinned source both had SHA-256 `891bdb4c8d3ac3b7771ba6f653279ccf299ddb2ca0c4fd8748e2e17b71e7a11f`. The separate native Codex CLI, version `0.166.0-alpha.1`, reported a cached ChatGPT login. It stopped before creating a model turn when opening `$CODEX_HOME/installation_id` for writing returned `EROFS`. The hosted sessions above ran independently of that CLI. A native second-model comparison requires a signed-in, writable CLI runner. Production rollout remains pending a measured improvement.
