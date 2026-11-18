# Held-out album delivery

The [frozen comparison](manifest_protocol.md) used four fresh pairs across GPT-6.2 Sol High and GPT-6.1 Sol High. Each worker inherited the same import retry, the preview error and a client manifest with blanks and duplicate rows. Worker-facing files preserved the data contract, both dated sidecars and the broken viewer. Before the first launch we removed a README sentence that would have told the worker exactly when to use the sidecar. On the primary route the spool contained all necessary captions. The twin needed the current sidecar for two of the four takes.

| First-pass outcome | Baseline | Candidate |
|---|---:|---:|
| Correct Harbor Walk manifest, protected inputs | 4/4 | 4/4 |
| Exporter also correct on unseen retry | 1/4 | 3/4 |
| Primary route, unseen retry | 0/2 | 1/2 |
| Sidecar route, unseen retry | 1/2 | 2/2 |
| GPT-6.2 Sol High, unseen retry | 1/2 | 1/2 |
| GPT-6.1 Sol High, unseen retry | 0/2 | 2/2 |
| Sustained detours | 0/4 | 0/4 |
| Side calls on optional route | 0 | 0 |
| Side calls across both routes | 1 | 0 |
| All shell calls | 26 | 22 |
| Median seconds to first useful action | 8.60 | 9.01 |
| Median seconds to first terminal reply | 68.40 | 52.59 |

Each worker regenerated four correctly captioned rows in capture order. The unseen test then changed the take IDs and filenames, varied the captions and supplied the only caption for one take on a retry. Four exporters discarded that later receipt. They handled the visible file but failed the source fix on a new batch. The visible README specifies which filename to preserve. It leaves caption precedence on later receipts implicit. This limits how broadly to interpret a failure on that unseen case. A working implementation could preserve both the first filename and the later nonempty caption.

Across their assigned packets, the two blinded graders recorded eight visible deliveries, four unseen failures and zero sustained detours. They split on how to score false completion. One called two unqualified exporter-fix claims false done because the fixes failed new inputs. The other credited the two other failed runs' claims about the specific client file and documented the overbroad implications. One baseline reran the failed preview for 0.077 shell seconds on the route that needed the sidecar. Both graders found no case of repeated no-progress actions or missed inputs required to deliver the visible client batch. No operator nudge was sent in this holdout.

The small correctness difference is worth sharing with the completion-eval owner. Both GPT-6.1 pairs account for that difference. There was no difference in side calls on the optional route and no replicated sustained detour. The [pressure study](pressure_results.md) also found equal unassisted handoff counts and conflicting evidence for its two detour labels. The frozen shipping condition was not met. No shared instruction, hook, release or installation changed as a result of this study.

## Reproduce the artifact check

From this directory, extract the [eight run records](evidence/manifest-trials.tar.gz). The checker verifies the pinned prompt and instructions, launch record, run identity, last recorded file hashes and graded packet hash. It runs each archived exporter on unseen data and compares the delivered client file and original sources. The [summary](evidence/manifest-summary.json) preserves each grader's rationale and exact checks. The graders were blind to arm and model, with one primary grade per trajectory. The first grader also replayed all 22 shell actions in its four packets and checked their target hashes.

```sh
album_dir=$(mktemp -d)
tar -xzf evidence/manifest-trials.tar.gz -C "$album_dir"
python -B manifest_proof.py replay "$album_dir" > "$album_dir/summary.json"
cmp evidence/manifest-summary.json "$album_dir/summary.json"
```
