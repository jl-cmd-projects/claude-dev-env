---
name: second-account-workers
description: >-
  Run local headless Claude workers through the account picker.
  Triggers: spawn a worker on the second account or another extra account, offload a worker,
  use a named Claude profile, save main account usage, run a local orchestrator that spawns
  and watches Claude workers.
---

# Extra account workers

Use this skill when a task needs a local Claude worker and the session should
save main account usage.

## Configure extra profiles

Run `claude_account_profile.py --profile-name NAME` for each extra profile.
The script creates `<profiles root>/NAME` and the `claude-NAME.cmd` launcher.
Running it again with the same name leaves the profile and launcher in place.

To set worker order, put `extra-profiles.json` in the main Claude home. Write a
JSON list of profile names, with the first choice first. Names use letters,
digits, hyphens, and underscores. The worker uses the existing second profile
when the file is absent. When the file exists, its list sets the full order.
Keep `main` and `wait` out of the list because they name picker decisions.
The picker keeps each account that has room and gives the job to the first one
listed in `claude-account-order.json` in the main Claude home. Unlisted accounts
follow, by most room left.
For direct picker calls, `--second-config-dir` sets the first extra profile and
each `--extra-config-dir` adds another in the order given.
Picker JSON prints `config_dir` for the choice and meters under `main`, `second`,
`extra_2`, and later labels.

## Choose a worker

Keep the Agent tool for small, fast lookups. For any worker that edits code,
researches at length, or runs long, give it its own Git worktree, write a
standalone brief to a file, and launch the account worker in the background.

```bash
python "$HOME/.claude/scripts/claude_account_worker.py" \
  --prompt-file "<brief>" \
  --cwd "<worktree>" \
  --report-file "<report>" \
  >"<worker-log>" 2>&1 &
worker_pid=$!
wait "$worker_pid"
worker_exit=$?
cat "<report>"
```

Add `--live-log "<events.jsonl>"` to watch the worker while it runs. The worker
then writes one JSON event per line into that file as it happens. Every event
carries the `session_id`, from the first startup hook line on. Each `assistant` line names the tool
calls and text, and the last line is the `result` event. Read new lines with
`tail -n 20 "<events.jsonl>"` and skip screenshots unless a check needs to see
the screen.

Read the JSON report and worker log after the process ends. The JSON fields are
`account`, `reason`, `exit_code`, `duration_seconds`, `result`, and `is_error`.
The runner writes one summary line with the selected account, exit code, and
report path.

When the command exits 3 and the report has `"account": "wait"`, no account is
eligible. Report the picker's reason and reset time. Do not fall back to the
Agent tool. Claude can also return exit 3 after a worker starts. When the
report account is `main`, `second`, or `extra_2` and later, report the child's
exit code and result. Exit 124 with reason `timeout` means the worker ran past
`--timeout-minutes`.

Workers never commit, push, or call `gh`. The calling session reviews each
worktree diff and owns every Git step.

## Write a standalone brief

When pstack is installed, the first brief line is `/pstack:poteto-mode`.
Otherwise, begin with the worker role. Include every detail needed to finish
without the calling session's conversation.

```text
/pstack:poteto-mode
Role: <one worker duty>
Owned files: <exact paths this worker may edit>
Acceptance checks:
- <observable behavior>
- <commands to run and expected result>
Report:
Changed: <files and reason>
Proof: <checks run and last result lines>
Blocked: <open issue, or none>
```

Keep the owned file list closed. Name the worktree path with `--cwd` and use a
separate brief and report path for each worker.

## Run a local orchestrator

To save usage in a long session, start one local orchestrator worker and let it
spawn the other workers. Give it its own brief that names each worker brief,
worktree, report path and live log. It launches each worker with the command
above in the background, reads the live logs to follow progress, and reads each
report at the end. Each spawn goes through the picker, so every worker lands on
the account with the most weekly room at its start.
