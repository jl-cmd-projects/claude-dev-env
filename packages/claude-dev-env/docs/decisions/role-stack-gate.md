# Role-stack gate

The first-task hook is the control. A rewrite ships only when `refusal_reason` in `hooks/session/deepen_role_gate.py` returns no reason. The skill, the wording rule, and the review rule cite this function. They do not restate it.

## What the unchanged hook did

Recorded before this gate edited `deepen_first_prompt.py`, with `CDE_DEEPEN_OUTPUT=json` on stdin.

The paste path, a first task and no rewrite stub, printed `decision` `deepen`. The rewritten prompt restated the four question stems and ended by telling the same agent to do the job.

The filled four-answer stub printed `decision` `deepen`. The rewritten prompt carried the four answer lines and no role lines.

## What the gate refuses

| Reason | When |
|---|---|
| `restates-four-questions` | The rewrite contains every canonical question stem. The paste path is this case. |
| `missing-role-lines` | `SCOPE (role):`, `EXAMPLES (illustration only):`, or `ZOOM-IN BLOCKER:` is missing or blank. |
| `example-noun-in-scope` | The scope line contains an example noun and `ZOOM-IN BLOCKER:` is `none`. |
| `dropped-hard-constraint` | A bullet under `HARD CONSTRAINTS` in the task is absent as its own line in the rewrite. |

Json mode prints `{"decision": "refuse", "reason": "..."}`. Rewrite mode and the command-hook path print nothing, so the prompt-submit mod leaves the submitted text in place.

## Proof shape

Run the hook on stdin with `CDE_DEEPEN_OUTPUT=json`. The paste path refuses. A role rewrite that leaves the example noun out deepens. Removing `refusal_reason` from `decide_first_prompt` lets the paste path deepen again, and `test_should_refuse_the_paste_path_as_the_known_bad` fails. The wrong twin puts the example noun in the scope line with `ZOOM-IN BLOCKER: none` and is refused.

`hooks/session/grade_role_stack_replay.py` scores a fixture whose task names one failure as an example. It calls `refusal_reason` and does not rewrite.
