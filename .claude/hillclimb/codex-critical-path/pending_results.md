# Does a redirect work when the worker is about to repeat a check?

The fresh reader changed behavior at the place where the prior trigger had missed it. Both unassisted workers reran a delayed-retry probe whose answer was already in the opening receipt. Both workers shown independent advice used that receipt and skipped the duplicate. The portable instruction alone prevented one of the two reruns. All six workers on the genuinely incomplete receipt ran a new delayed probe with distinct transport IDs. Their command logs and saved output confirm the repairs.

## What was compared

Each of six matched groups had three fresh hosted solvers. One used the existing instructions, one received the additional paragraph, and one had a separate GPT-6.2 Sol High session review its pending command. For each of the two ledger conditions and the gallery transfer reserve, one triplet used GPT-6.2 Sol High and one used GPT-6.1 Sol High. Worker, reviewer and dispatch receipts record the accepted selectors and returned worker identities. Independent server-side model identity and billed token counts were unavailable.

All three conditions began from the exact same visible checkpoint for their case. The ledger histories included two prior worker actions and their outputs, the checkout and the next *proposed* command from the earlier study. One existing receipt qualified. Its counterpart never reached the target branch. The reserve preserved six prior gallery actions and the already-produced artifacts. Its pending command mixed redundant Git checks with a useful final read. No solver saw what the original worker did after the recorded proposal. The fresh workers received the observable histories. The original workers’ private model state was unavailable. The reserve came from a different task in an earlier study. It supplied a transfer test without supplying a new field incident.

Every reader could compare the original goal, the exact proposal, earlier actions and visible files. The two readers of valid opening receipts sent concrete advice. The two readers of invalid receipts and both gallery readers returned PASS. Only the two substantive redirects appeared in solvers' sessions. All 18 solvers submitted in the 360-second active budget. Zero actual operator follow-ups were sent during the experiment.

## Delivery and independent assessment

Each count below covers six solvers per arm. Where two numbers appear they are the separate grades of the preregistered primary reader and the second reader. Both saw the same sealed actions and artifacts.

| Observation | Unchanged | Portable instruction | Fresh review |
| --- | ---: | ---: | ---: |
| Unnecessary delayed probe executed, receipt already valid | 2/2 | 1/2 | 0/2 |
| Necessary delayed probe executed, receipt incomplete | 2/2 | 2/2 | 2/2 |
| Gallery worker retained prior verification and omitted the entire pending command | 0/2 | 1/2 | 0/2 |
| User's requested work delivered, primary / second | 6 / 5 | 6 / 6 | 5 / 5 |
| User follow-up judged necessary, primary / second | 0 / 1 | 0 / 0 | 1 / 1 |
| Two or more avoidable operations, primary / second | 2 / 2 | 0 / 0 | 2 / 1 |
| Strict machine-plus-reader delivery, primary / second | 5 / 4 | 4 / 4 | 3 / 3 |
| Median active seconds to first useful action, primary / second | 8.44 / 9.33 | 8.38 / 8.38 | 18.65 / 18.65 |

Both readers credited supporting verification in all 18 cases and all six dependency repairs. They independently flagged the same Sol 6.2 gap worker in the reviewer arm as prematurely finished. The reviewer had returned PASS. The primary reader found the plan lacked a pre-commit interruption test for partial writes. The second found the requested short-burst comparison missing. That reader also found the comparison missing from one Sol 6.2 baseline plan. The primary reader accepted that plan. Both accepted all six instruction-arm deliveries. The median time to first useful action in the instruction arm covers five workers. The sixth could finish from previously verified files without issuing another command.

Both readers marked the same two baseline workers as meeting the two-operation detour threshold, and neither marked an instruction worker. These were brief extra checks. The readers agreed that one reviewer-arm worker also met the threshold and disagreed on a second. The single operator nudge in the historical workstation exchange remains a field observation. In this experiment both readers inferred the need for follow-up from the artifacts. All 18 workers submitted without receiving a nudge.

The original mechanical oracle rejected all 18 artifacts. The more flexible check, frozen before solver launches, accepted 13, distributed 5/6, 4/6 and 4/6 across baseline, instruction and review. A separate scratch replay tested the five rejections. Two valid acceptance CSVs contained additional cases beyond the three required rows. Three workers had executed the ledger probes through a Python or Markdown wrapper that the command parser missed. In all five scratch workspaces the replay reproduced the archived file bytes and action state hashes. That establishes execution and file integrity. The semantic assessment separately asks whether the design would prevent a duplicate debit and whether its acceptance plan could catch a broken implementation.

## Costs and decision

The six independent reader calls consumed 56.10 active seconds altogether. The reviewer arm took longer than baseline on every matched triplet, including the two where the unnecessary action was avoided (+9.10 and +46.81 seconds). The median within-triplet change in completion time was +6.46 seconds with review and +4.69 seconds with the portable instruction. The instruction was slower in four of six triplets. These differences include worker variability. Dispatch and queue delays appear separately from solver work.

On GPT-6.1 Sol High, the portable instruction worker skipped the target rerun and its gallery counterpart relied on still-valid prior verification. The GPT-6.2 Sol High instruction workers reran the delayed probe and executed the gallery command. All four gallery workers in the baseline and reviewer conditions executed the substantive operations in that command. The gallery readers offered no redirect. The reviewer was deliberately placed at selected recorded proposals. A production selector for finding such proposals automatically has not been validated. Both readers counted fewer repeated operations without a delivery regression in the instruction arm, and one of its two reserve workers retained earlier verification. The baseline delivery difference rests on a single disputed case. This leaves prevention of a prolonged diversion that would require an operator nudge unproven. No production behavior change was proposed, merged or activated from this round.

## Replay

Run from this directory using Python 3 and a Git checkout with the pinned baseline. The previously checked-in design archive is the independent source of the three recorded decisions. Preserve file modes when extracting.

```sh
run_dir=$(mktemp -d)
tar -xpzf evidence/pending-trials.tar.gz -C "$run_dir"
python -B pending_verify.py replay "$run_dir" \
  --annotations "$run_dir/pending_blind_grades_secondary.json" \
  --output "$run_dir/recomputed.json"
cmp evidence/pending-summary.json "$run_dir/recomputed.json"
python -B pending_failure_audit.py "$run_dir" "$run_dir/recomputed.json" > "$run_dir/mechanics.txt"
cmp "$run_dir/mechanical-reread.txt" "$run_dir/mechanics.txt"
```

[Preregistered comparison](pending_protocol.md) · [Run and reader breakdown](evidence/pending-summary.json) · [Archived checkpoints, sessions and assessments](evidence/pending-trials.tar.gz)
