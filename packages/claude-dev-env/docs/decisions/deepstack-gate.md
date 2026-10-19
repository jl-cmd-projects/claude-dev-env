# DeepStack gate

The first-task hook is the control. A rewrite ships only when `refusal_reason` in `hooks/session/deepen_role_gate.py` returns no reason. DeepStack, the wording rule, and the review rule cite this function. They do not restate it.

## What the unchanged hook did

Recorded before this gate edited `deepen_first_prompt.py`, with `CDE_DEEPEN_OUTPUT=json` on stdin.

The paste path, a first task and no rewrite stub, printed `decision` `deepen`. The rewritten prompt restated the four question stems and ended by telling the same agent to do the job.

The filled four-answer stub printed `decision` `deepen`. The rewritten prompt carried the four answer lines and no role lines.

## What the gate refuses

| Reason | When |
|---|---|
| `restates-four-questions` | The rewrite contains every canonical question stem. The old paste path was this case. |
| `missing-role-lines` | `SCOPE (role):`, `EXAMPLES (illustration only):`, or `ZOOM-IN BLOCKER:` is missing or blank. |
| `example-noun-in-scope` | The scope line contains an example noun and `ZOOM-IN BLOCKER:` is `none`. |
| `dropped-hard-constraint` | A bullet under `HARD CONSTRAINTS` in the task is absent as its own line in the rewrite. |

Json mode prints `{"decision": "refuse", "reason": "..."}`. Rewrite mode and the command-hook path print nothing, so the prompt-submit mod leaves the submitted text in place.

## The default rewrite

With no rewrite stub and no `CDE_DEEPEN_COMMAND`, `hooks/session/deepen_default_rewrite.py` builds the rewrite. It takes the scope from the task's own sentences, moves clauses the task marks as examples (`for example`, `for instance`, `e.g.`, `such as`) to the examples line, clips a scope over 240 characters with a pointer to the full task, copies the task with its hard constraints, and ends with one order to do the job. When the scope still names an example, the blocker line asks the worker to confirm before narrowing to it. The gate checks this rewrite like any other, so a first task deepens on every host with nothing configured.

## Proof shape

Run the hook on stdin with `CDE_DEEPEN_OUTPUT=json`. A stub that pastes the four question stems refuses, and the default rewrite deepens. A role rewrite that leaves the example noun out deepens. Removing `refusal_reason` from `decide_first_prompt` lets the paste path deepen again, and `test_should_refuse_the_paste_path_as_the_known_bad` fails. The wrong twin puts the example noun in the scope line with `ZOOM-IN BLOCKER: none` and is refused.

`hooks/session/grade_deepstack_replay.py` scores a fixture whose task names one failure as an example. It calls `refusal_reason` and does not rewrite.
