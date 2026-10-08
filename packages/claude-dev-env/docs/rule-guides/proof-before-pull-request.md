Back to the [rule entry](../../rules/proof-before-pull-request.md).

# Proof before a pull request

**When this applies:** Every session that builds a change and opens a pull request, in every project.

## Rule

Before you open a pull request, prove the change does its job where it will run.

What counts as proof:
- You ran the changed thing the way its user runs it, and you saw the effect it exists to produce. A hook fires in a live Claude Code session and changes what that session does. A script runs from its launcher on inputs like the ones it will meet. A skill or rule changes what a fresh agent does with an ordinary request.
- You saw the failure first. Run the same scenario without your change and record what goes wrong. The proof is the difference between the two runs.
- You covered the conditions the change will meet. That includes the case it should leave alone, and for session behavior a fresh session, a resumed session, a later turn, and a session after compaction.
- The session under test got an ordinary request, worded as a task the way Jon would ask for it.

Unit tests are welcome as extra evidence. The live run is the proof. A test you edited until it passed proves nothing.

For a change to Claude Code behavior, such as a hook, skill, rule, setting, prompt or output style:
- Spawn every session through the account broker, with the stream saved to a file:
  python ~/.claude/scripts/account_broker.py run --product claude --report <broker-report.json> -- claude -p "<request>" --model claude-opus-5-5 --effort <level> --output-format stream-json --verbose > <stream.jsonl>
- Run each later turn the same way with `--resume <session id>`. The broker resumes a session on the account that started it when that account has room.
- Keep `--model` and `--effort` on every call. Without them the headless run uses claude-sonnet-5-5. Confirm the served model in the result's `modelUsage`.
- Start the broker from your own shell, with your environment as is. The broker reads the account meters with your session's credentials and starts Claude without your session's variables.
- Leave out `--bare` and `claude plugin eval`. Both drop the hooks and settings the user runs with.
- Read the broker report for the account it chose. Read the stream for the hook events and their output, `permission_denials`, the final result, and the token usage on the result event.
- When the broker exits 3 with action "wait", no account has room. Treat that as a blocked proof and report its reason and `resets_at`. Spawn Claude only through the broker.

Report it in the pull request body under "Proof in practice". List each command you ran, quote the output lines that show the effect, state the difference between the runs with and without the change, and name anything still unproven.

When you cannot prove it, leave the pull request unopened. Tell Jon in three short sentences what you could not run and which tool would make it possible. A blocked proof is an acceptable result, because it shows where tooling is missing.

## Enforcement

`hooks/blocking/pull_request_proof.py` reads the body of each new pull request before it opens. `pr_lifecycle_skill_gate.py` runs it on `gh pr create`, the `pull_request.py create` script, and each `mcp__*__create_pull_request` tool. The gate denies the call when the body has no "Proof in practice" heading, or when the text under that heading names no command in backticks. A `gh pr create` with no `--body` or `--body-file` is denied with a request for the body. Edits, merges, and pushes pass.

When the checked-out branch changes a file people see (`.html`, `.htm`, `.css`, `.scss`, `.tsx`, `.jsx`, `.vue`, `.svelte`), the gate also denies a body whose proof section holds no picture: a markdown image, an image URL, or an Artifact page link that shows the screenshots. Render the change, read the screenshot, and put it in the section, so the reader sees what you looked at. When git in the session directory cannot list the branch's changed files, the gate asks for the picture as well.

The gate checks that the section is there and names a command. Whether the run proves the change stays a judgment for the author and the reviewer.
