# One installed copy

This package holds the one copy of efficient-review, at `packages/claude-dev-env/.agents/skills/efficient-review/`. A fresh install copies that directory to `~/.claude/skills/efficient-review` and `~/.agents/skills/efficient-review`.

A session in any repository runs the review from that installed directory. It does not check out a second repository, name a workflow, or read a credential.

## Plan

From the skill directory:

```
python -m tools.efficient_review plan
```

On Claude, `CLAUDECODE` or `CLAUDE_CODE_ENTRYPOINT` is set and Cursor and Codex markers are absent. The plan selects haiku and the slim profile from `hooks_constants.haiku_spawn_slim_gate_constants`, and prints the headless command and its environment. Run that command. Send the review task on standard input. The criteria are in [reference/criteria.md](reference/criteria.md).

On any other platform, including a plain shell, the plan defers the model. The running agent follows [SKILL.md](SKILL.md) and picks the model.

The constants module is the copy installed with this package's hooks, at `hooks/hooks_constants/haiku_spawn_slim_gate_constants.py` next to the skills directory, or inside a checkout of this package. The plan does not carry a second profile.

## A local job in another repository

A repository that wants a job to run the review writes that job itself. This package does not ship one. The job runs the same plan from the installed skill directory, then follows [SKILL.md](SKILL.md).

```yaml
- name: Plan the review
  working-directory: the installed skill directory
  run: python -m tools.efficient_review plan
```

## What a consuming repository deletes

Delete the vendored skill and the runner that existed only to launch it:

- `.claude/skills/efficient-review/`
- `tools/efficient_review.py`
- `tools/efficient_review_launch.py`
- `tools/efficient_review_request.py`
- `tools/config/efficient_review_constants.py`
- `.claude/hooks/efficient_review_model_gate.py`
- `.claude/hooks/efficient_review_model_gate.sh`
- `.claude/hooks/config/efficient_review_model_gate_constants.py`

Also delete a vendored slice of `tools/review_profile`, `tools/review_command`, `tools/review_rules`, `tools/review_stream`, and `tools/review_codex` when that slice exists only so the old runner could import it. Delete a settings file whose keys named a workflow, a checkout credential, a roster, or a broker. Keep `tools/review_model_eval` when the repository still grades reviews with it.
