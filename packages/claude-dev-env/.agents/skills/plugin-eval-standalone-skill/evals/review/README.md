# Review evaluation

This is a first evaluation of the `e-code-review` low-effort recipe. It measures whether a fresh model detects a documented correctness defect and avoids reporting a defect on a clean hunk. It supplies the recipe as prompt text and adapts its final response to structured JSON. It does not measure skill discovery, tool execution, the higher review levels, repository navigation, fixes, or PR delivery.

## Cases and labels

`cases.json` contains 16 controller-authored synthetic cases drawn from defect classes named in `e-code-review/reference/low.md`. It has seven bug cases and nine clean cases. Ten cases are development cases; six are held out by related-case group. The cases cover the recipe's stated defect classes. Production traffic frequencies remain unmeasured. They need human review before use as a release gate. Add minimized historical accepted and rejected review findings next, with source commit references and privacy review.

Each case includes a resulting-code witness, its intended value, and its observed value. `validate` executes these trusted, repository-authored snippets in bounded isolated Python processes. Never substitute model-written code into this validation path. Bug witnesses disagree with the contract; clean witnesses agree. Each witness proves the behavior of one input. Broader function correctness remains unmeasured.

The model sees the contract, diff, recipe and response schema. It receives no case ID, group, witness, expected labels or split. Each call uses a separate read-only working directory. Trace inspection rejects command, MCP, search or file-change events. Read-only sandboxing does not make unrelated local files inaccessible; this is a tool-free recipe experiment, not a security isolation guarantee.

## Rubric and failure taxonomy

A finding matches only when its category and resulting-file line match a labeled finding. A repeated finding counts once toward recall and each extra copy counts as a false positive. A wrong location counts as both a miss and a false positive. Clean cases require an empty findings array. A nonempty failure scenario is required, but its semantic correctness is not machine-graded. Read scenarios manually before trusting conclusions. No model judge is used because detection and location have deterministic labels. Subjective scenario scoring can be added only after calibration on human-labeled good, bad and borderline outputs.

Report finding precision and recall, clean-case specificity and false-positive rate, exact-case pass rate and its Wilson interval separately. The interval describes this small case set under an independence assumption; related pairs and handpicked cases limit generalization. A misplaced or invented finding, missed defect, duplicate finding and schema failure remain distinct. Launcher/provider errors, timeout and unexpected tools remain infrastructure failures outside the task denominator. Output errors appear separately and block promotion even if the scored subset passes. Do not compare runs with different scored case sets.

## Reproduce

From the repository root:

```powershell
$suite = 'packages/claude-dev-env/.agents/skills/plugin-eval-standalone-skill/evals/review/run.py'
python $suite validate
python -m pytest packages/claude-dev-env/.agents/skills/plugin-eval-standalone-skill/evals/review/test_run.py -q
python $suite live --limit 2 --timeout 90 --model gpt-6.1-sol --effort low --output review-smoke
python $suite live --split heldout --limit 6 --timeout 90 --model gpt-6.1-sol --effort low --output review-heldout
```

On Windows, pass `--codex <absolute-path-to-codex.exe>` when the shell launcher cannot run through `subprocess`. The adapter uses the existing login, `codex exec --json --output-schema`, ignores user config, and preserves account authentication. It never installs a service or creates credentials. Choose the account's supported model explicitly.

Before each model run, record CLI and Python versions, model, effort and estimated usage. The default smoke makes at most two calls with 90-second ceilings and a three-minute batch ceiling. `--max-seconds` bounds the model-call portion of any batch and accepts at most 600 seconds. It stops on the first infrastructure failure and has no retries. The runner cannot enforce a dollar budget because the CLI does not expose a documented dollar cap here. Account billing varies; a larger run requires an agreed estimate first. The bounded CLI timeout stops the child process but cannot guarantee upstream cancellation. A run with a failed, invalid or missing attempt returns status 1.

Every output directory is new. It holds prompts, raw JSONL traces, stderr, captured responses, per-case latency, usage where supplied, requested model and effort, input/recipe/dataset hashes, and summary metrics by split. Preserve these artifacts with the source commit and CLI version. Do not commit account traces until checked for sensitive paths and account metadata.

Replay accepts a JSON object mapping case IDs to structured responses:

```powershell
python $suite replay --responses saved-responses.json --limit 16 --split all --output review-replay
```

Replay scores stored outputs; it makes no model calls. `validate` exercises witnesses and good/bad grader controls; it makes no model calls. `live` runs a fresh model with fixture inputs and the adapted recipe. None of these modes runs the complete repository review workflow. A passing replay or unit suite does not establish model performance.

Keep held-out groups out of prompt edits. After repeated inspection, retire them as development data and create a new human-reviewed holdout. Freeze the incumbent responses and compare candidate results on matched cases, model settings and repetitions. The current set cannot justify small percentage improvements or deployment decisions.

## Sources

- [Claude build-eval source](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/evals/build-eval.md): inputs, application runner, grader and reviewed pilot.
- [OpenAI skill evaluation guide](https://developers.openai.com/blog/eval-skills): direct Codex execution, traces, structured grading and invocation negatives.
- [OpenAI migration guidance](https://developers.openai.com/cookbook/examples/evaluation/moving-from-openai-evals-to-promptfoo): portable evaluation workflows.

The suite adds no hosted Evals dependency. Keep the existing Claude plugin runner for discovery and with/without-plugin experiments; use this deterministic review suite for output correctness.
