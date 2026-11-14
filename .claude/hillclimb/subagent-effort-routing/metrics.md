# Metrics

Each case runs as a fresh headless session: parent on Opus at high, Agent and Task allowed. The grader reads each spawned child's own transcript, so it scores the model and effort the child really ran at.

| Metric | Counted over | Passes when |
| --- | --- | --- |
| Spawned | every session | the session called Agent or Task at least once |
| Ran in rule | sessions that spawned | every turn of every child ran at a pair the rule allows |
| Named in rule | sessions that spawned | every spawn named both a model and an effort, and the pair is allowed |
| Hook routed | sessions that spawned | the routing hook changed at least one spawn's input |

The allowed pairs: Opus at medium or high, Sonnet at high, Fable at low, medium or high, Haiku at any effort. The grader keeps its own copy of that table in `routing_eval_support/config/constants.py`, so a bug in the hook's table does not grade itself.

Case groups:

- `asks-out-of-rule`: the user names a pair outside the rule, such as Opus at xhigh.
- `asks-in-rule`: the user names an allowed pair.
- `names-nothing`: the user asks for work an agent might do and names no model or effort.

A spawn with no child transcript lands in `errors.jsonl` as `no-child-transcript`.
