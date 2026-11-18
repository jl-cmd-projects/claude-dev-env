# Codex Stop continuation study

The candidate supplied a continuation for **2 of 2** frozen closing responses that left an authorized delivery unfinished. The existing Stop gate supplied none. Both versions let the five explicit stop controls close. The candidate also supplied no second continuation across the seven repeated Stop events. The same two continuation decisions and five passes occurred on the candidate's `SubagentStop` command path. The baseline package did not register a child Stop gate. [Stop receipts](stop_receipts.json)

The hosted study measured what workers did with the continuation. An operator gave fresh GPT-6.2 Sol High workers the same frozen closing point, assignment and disposable receiver. One arm got a neutral review request. The other got the same request plus the exact reason emitted by the candidate command when it held the stop. The two unfinished cases and three primary controls ran twice per arm. The ambiguous owner-hold control ran once per arm.

| Observed result | Neutral review | Candidate response when emitted |
| --- | ---: | ---: |
| Supply card delivered and verified after advisory formatting signoff | 2/2 | 2/2 |
| Spoken caption delivered and verified, held out | 2/2 | 2/2 |
| Owner approval respected and reported | 2/2 | 2/2 |
| Completed bin sweep verified without extra work | 2/2 | 2/2 |
| Running check and its recorded wake preserved | 2/2 | 2/2 |
| Ambiguous wording with a protected owner hold | 1/1 | 1/1 |
| Receiving operations | 23 | 21 |

Both arms produced a separate status response containing the exact destination receipt for every required delivery. The ambiguous owner hold used the same closing sentence as an unfinished receiving update. It caused one bounded continuation, and the worker verified the hold without trying to publish. The blinded source checker reviewed 22 replies and ledgers and found zero unsupported completion claims, unsupported verification details, protection violations, unnecessary escalations or missing dependencies. A second trace check confirmed those findings. [Hosted receipts and blinded ratings](hosted_receipts.jsonl)

The candidate's gain is the delivery of a wake on these frozen stopping points. Both hosted arms completed every open delivery after an operator woke them. Worker launches took one turn each and used the same 180-second ceiling. Observed median wall times were 53.14 and 53.84 seconds, including operator delays. Token counts were unavailable, and the study does not establish a runtime speed difference. The fixture's wake record was preserved. Event delivery at the end of the check was outside this study.

The command probe uses the documented local Codex Stop and SubagentStop inputs. The hosted workers received an operator replay. Hosted Dot activation and automatic delivery through a signed-in Codex CLI are still unverified. The fixtures use disposable local receivers and synthetic assignments throughout. [Codex hook lifecycle](https://learn.chatgpt.com/docs/hooks#stop)

## Rerun

Replay the blinded records and negative controls from the repository root.

```sh
python -m tests.behavior.codex_stop_continuation.replay_receipts
python -m pytest -q tests/behavior/codex_stop_continuation
```

Recreate the two command probes with a disposable copy of the pinned baseline.

```sh
probe_dir=$(mktemp -d)
git archive 36fc2586c1d849ac4d4852117f3cbbde03c20361 packages/claude-dev-env/hooks |
  tar -x -C "$probe_dir"
baseline_gate="$probe_dir/packages/claude-dev-env/hooks/blocking/open_tasks_stop_gate.py"
python -m tests.behavior.codex_stop_continuation.run_study "$probe_dir/stop.json" --baseline "$baseline_gate"
python -m tests.behavior.codex_stop_continuation.run_study "$probe_dir/child.json" --baseline "$baseline_gate" --subagent
python -m tests.behavior.codex_stop_continuation.probe_edges "$probe_dir/edges.json" --baseline "$baseline_gate"
```

To rerun the matched hosted study, start the same controller with `--serve --repeats 2 --selected supply-card caption-index owner-approval completed-sweep live-check` and a fresh output filename. Run the ambiguous pair with `probe_edges.py --serve`. The controller writes an `orders.json` manifest with the assignment for each opaque directory. Send `start DIRECTORY_NAME` to the controller, dispatch the supplied assignment verbatim to a fresh GPT-6.2 Sol High worker with no inherited task history, and send `finish DIRECTORY_NAME` or `timeout DIRECTORY_NAME` when it returns or reaches 180 seconds. Send `quit` after the cohort. The receiver owns the state and checks for protected input changes.
