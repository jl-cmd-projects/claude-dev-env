# First baseline, 2026-09-30 UTC

Four fresh Codex calls passed four synthetic review cases. This measures the adapted low-effort recipe with fixture inputs. It does not measure installed skill discovery, repository review, review fixes or production performance.

After the repository policy gate required smaller typed functions and separate configuration, the refactored runner repeated the two development cases with fresh model calls. Both passed again. The bug case took 9.676 seconds with 25,435 input tokens and 80 output tokens. The clean case took 9.339 seconds with 24,888 input tokens and 41 output tokens, including 22,144 cached input tokens. The repeat used the same model, effort, dataset and recipe. It adds two fresh attempts on existing cases, so unique case coverage stays at four. Across the initial baseline and integration repeat, six calls passed with 51.684 seconds of summed model-call latency, 150,412 reported input tokens and 375 reported output tokens. The final smoke's entry-point SHA-256 is `f9529e3be3561dec2ad5f0c07e18b5f8c35596bb87ed2b3da9bf08ddf25914d9`. Its working tree included the policy refactor before that refactor was committed.

| Case | Split | Expected | Model response | Seconds | Input tokens | Output tokens |
| --- | --- | --- | --- | ---: | ---: | ---: |
| zero-bug | development | falsy-zero at line 2 | falsy-zero at line 2 | 8.897 | 25,431 | 73 |
| zero-clean | development | no findings | no findings | 7.325 | 24,884 | 47 |
| catch-bug | heldout | swallowed-error at line 5 | swallowed-error at line 5 | 9.578 | 24,884 | 83 |
| catch-clean | heldout | no findings | no findings | 6.869 | 24,890 | 51 |

The two bug scenarios name concrete inputs and consequences. The preserved model text is in [baseline-responses.json](baseline-responses.json). Manual inspection agrees with the executable witnesses for these two replies. Semantic scenario grading remains uncalibrated.

Development precision and recall are 1/1. Clean specificity is 1/1 and false-positive rate is 0/1. Held-out precision and recall are 1/1. Clean specificity is 1/1 and false-positive rate is 0/1. Each split's exact-case pass rate is 2/2, with a 95% Wilson interval of 34.2% to 100%. Small related pairs make these numbers insufficient for a release decision. No repeated-run variance or with/without-skill comparison was measured.

Total model-call latency is 32.669 seconds. Reported input usage totals 100,089 tokens; reported output usage totals 254 tokens. These counts include CLI context and are not the size of the case prompts alone. Account dollar cost is unavailable. No new credentials or paid service were created. Runs used the existing ChatGPT account, `gpt-6.1-sol`, low effort, Codex CLI 0.159.2 and Python 3.13.5 on Windows. The model identifier is the requested identifier; independent provider identity attestation is unavailable in these traces.

Two earlier startup probes produced no scored outputs. The workspace sandbox prevented CLI app-server initialization. After permission for the same read-only smoke outside that outer sandbox, the shorthand model `gpt-6.1` was rejected as unsupported for this account. The successful runs used the account's configured identifier, `gpt-6.1-sol`. These startup failures remain infrastructure results and do not count as missed bugs.

All 16 cases have passing before/after executable witness checks. All 16 known-good grader controls pass and all 16 deliberately broken controls fail. These are controller-authored validation results with zero model calls. They do not contribute to the model score. Stored replay responses are in [baseline-responses.json](baseline-responses.json); replaying them also does not create fresh evaluation coverage.

Dataset SHA-256 is `698a370de7aebb4051e7a02fd4f3dfff623d879a69970538e62f79535ca82cbe`. Recipe SHA-256 is `556fd92a7a0d60c5584adc48c3b0093ff2fb092f773a5011e9aa68720bd8de34`. The source checkout was isolated from `jl-cmd/claude-dev-env` and the proposal was moved onto main commit `0beb80ca` after the first smoke. The review recipe and dataset hashes stayed unchanged. Final harness hardening adds trace/output identity validation and before-state witness checks. The four saved traces pass the final trace checks without another model call.

The fresh traces, stderr, captured replies and JSONL results remain in the task workspace under `evidence/smoke-4`, `evidence/heldout-smoke` and `evidence/final-refactored-smoke`. They are separate from the proposal repository. Account and thread metadata are not published in the draft. Twelve cases remain unrun. Four held-out cases remain unopened by model execution. Human label review, historical cases, independent scenario grading and an installed-skill invocation evaluation remain outstanding.

## Coverage inventory

| Workflow | Inspected capability | Gap and next evaluation |
| --- | --- | --- |
| Review correctness and false positives | `e-code-review` has five recipe levels. Review invocation and parser tests exist. The standalone eval skill documents Claude plugin trigger and ablation runs. | Before this proposal, the inspected review paths contain no labeled fresh-output correctness suite. This proposal covers four fresh low-effort fixture cases. Add accepted/rejected historical findings, missing-await cases, multiple findings, larger code context and invocation negatives. |
| Asset verification and nine-patch quality | Python's `verify-design-icon-pipeline/evals/run_evals.py` registers nine scenarios and accepts agent launchers. It distinguishes live-only, source-backed and fixture-pending cases. The nine-patch grader checks verdict labels and a required token. | Preserve this runner. Nine-patch and diagnose-a-bar remain fixture-pending in its registry. A transcript label match does not prove the saved asset or render is correct. Add controller-owned render/end-state checks and matched fresh runs, then calibrate visual judgment with human-labeled good, bad and borderline crops. |
| Transparent-alpha output | The Python skill has a separate transparent-alpha evaluator and checker proof scripts. | Audit source receipts, saved artifact hashes, image rendering and any fresh-model records before claiming end-to-end coverage. This proposal does not execute those scripts. |
| Collection brief and eligibility selection | This task has context from the concurrent collection work; the primary collection checkout was not inspected here. | Coordinate with that owner. Preserve eligibility constraints, source candidate IDs, time validity and coverage/diversity checks. Label qualified and near-miss exclusions; run selection against an isolated data snapshot. Coverage status remains unverified. |
| Buyer-comment drafting, translations and submission workflows | Python contains model-backed shared utilities and production pipeline code. Existing unit tests establish local contracts. | Inventory entry points, model calls and output side effects. Grade drafts separately from publishing. Use anonymized inputs, schema checks and groundedness review, then isolated end-state tests for any tool actions. No model evaluation was executed here. |

This inventory is bounded by the files inspected. It does not assert the absence of evaluation in every repository or run-history store.

## Skill discovery and implementation choice

The exact command's published source is [claude-api/shared/evals/build-eval.md](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/evals/build-eval.md). It builds inputs, an application runner and graders, obtains review of the inputs and grading, pilots examples, then records metrics and traces. Local plugin caches contain `skill-creator` evaluation scripts and the installed standalone plugin-eval skill. A local `claude-api` skill file was not found in the inspected skill/cache locations. The Claude launcher also fails at module startup because `ACTIVE_GUARD_DESKTOP_PROCESS_NAME_PATTERN` is missing from its constants module. No exploratory Claude agent was needed to read the published source.

The direct implementation follows [OpenAI's skill evaluation guide](https://developers.openai.com/blog/eval-skills), using `codex exec --json --output-schema`. It adds the output-quality suite to the existing evaluation skill. The proposal adds no second framework. Existing Claude plugin ablation remains useful for contribution and trigger behavior. [OpenAI's hosted evaluation migration guidance](https://developers.openai.com/cookbook/examples/evaluation/moving-from-openai-evals-to-promptfoo) supports keeping cases and scoring portable. This proposal adds no hosted Evals API dependency.
