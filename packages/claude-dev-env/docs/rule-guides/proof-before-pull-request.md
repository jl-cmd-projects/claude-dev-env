Back to the [rules index](../../rules/index.md).

# Proof before a pull request

## In brief

Run the change where it runs, with and without it, and quote both results under "Proof in practice" in the body. A hook denies a body without one. Unproven: leave it unopened and tell the user.

**When this applies:** Every session that builds a change and opens a pull request, in every project.

## Rule

Before you open a pull request, prove the change does its job where it will run.

What counts as proof:
- You ran the changed thing the way its user runs it, and you saw the effect it exists to produce. A hook fires in a live Claude Code session and changes what that session does. A script runs from its launcher on inputs like the ones it will meet. A skill or rule changes what a fresh agent does with an ordinary request.
- You saw the failure first. Run the same scenario without your change and record what goes wrong. The proof is the difference between the two runs.
- You covered the conditions the change will meet. That includes the case it should leave alone, and for session behavior a fresh session, a resumed session, a later turn, and a session after compaction.
- The session under test got an ordinary request, worded as a task the way the owner would ask for it.

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

Report it in the pull request body under "Proof in practice". List each command you ran, quote the output lines that show the effect, and state the difference between the runs with and without the change. The run on the target the change exists to fix belongs in this section before the pull request opens. List a condition the change does not target, such as an older data shape, under a "Not covered" heading at the same level.

A workflow file the pull request adds cannot run until it reaches the default branch. For that run only, add an "After merge" heading to the body. Under it, name the added workflow file in backticks and say who records the first run's link. Prove everything else the workflow does before the pull request opens, such as its script and tests.

When you cannot prove it, leave the pull request unopened. Tell the owner in three short sentences what you could not run and which tool would make it possible. A blocked proof is an acceptable result, because it shows where tooling is missing.

## Enforcement

`hooks/blocking/pull_request_proof.py` reads the body of each new pull request before it opens. `pr_lifecycle_skill_gate.py` runs it on `gh pr create`, the `pull_request.py create` script, and each `mcp__*__create_pull_request` tool. The gate denies the call when the body has no "Proof in practice" heading, or when the text under that heading names no command in backticks. The gate also denies a section whose only commands run a test runner, such as `pytest`, `python -m unittest`, `uv run pytest`, `npm test`, `npx vitest`, `jest`, `go test` or `cargo test`. Quotes around a runner word, interpreter flags before `-m`, and `coverage run -m unittest` are still test runs. A command is an inline backticked span or a `$ ` line inside a fenced block. A span that starts with a path and line, such as `gate.py:12`, is not a command. A span that holds one path or file name, such as `src/x.py`, is not a command unless that span runs a test runner, such as `py.test` or `pytest.exe`. A test run piped into `tee`, `tail`, `head`, `grep` or `cat` is still a test run. The deny quotes the line "Unit tests are welcome as extra evidence. The live run is the proof." and asks for a run of the changed thing the way its user runs it, without the change and with it. The gate also denies a section whose prose says part of the change is not proven, not tested or not verified, with "yet", "been" or "fully" allowed after the "not", or says unproven, untested or unverified. The line passes when the branch adds a workflow file under `.github/workflows` that the default branch lacks, and the body has an "After merge" heading whose text names an added workflow file in backticks and says who records the run, with no "nobody" or "not" ahead of the verb. Every unproven line in the section must also say GitHub Actions, "live run", "first run", "live workflow run" or "first workflow run", or name an added workflow file. The recorder check reads prose outside code spans and fenced blocks for "record", "records" or "recorded" followed within 30 characters by "run", "link", "url" or "result". One sentence of that kind is enough. A sentence does not count when "nobody", "not", "never" or a similar word comes up to 60 characters before the verb, or when the verb is followed by "nothing", "none" or "no". A period followed by a space, a semicolon or a line break ends a sentence. The backticked name is the added workflow file, by file name or by its full path. A file the branch renames or copies counts as added. Run `scripts/durable_post_lint.py` from a checkout of the repository the pull request targets, because it reads the added files from the session directory when that checkout's origin is the target repository and lists an added workflow, and from the GitHub compare API otherwise. Pass `--repository owner/name` to the lint. Without it the lint cannot list the added files, so it keeps the deny. The gate reads the added files from git in the session directory, or from the GitHub compare API when git cannot tell or lists none, and `scripts/durable_post_lint.py` passes `--head-branch` and `--repository` to it. A branch that only edits a workflow, or whose added files neither source can list, keeps the deny. Otherwise the deny quotes that line, and asks for the run before the pull request opens, or for the line under a "Not covered" heading when the change does not target it. Words inside backticks or a fenced block are quoted output and do not count. A section with one command that is not a test run, and no such line, passes. A `gh pr create` with no `--body` or `--body-file` is denied with a request for the body. Edits, merges, and pushes pass.

When the checked-out branch changes a file people see (`.html`, `.htm`, `.css`, `.scss`, `.tsx`, `.jsx`, `.vue`, `.svelte`), the gate also denies a body whose proof section holds no picture: a markdown image, an image URL, or an Artifact page link that shows the screenshots. Render the change, read the screenshot, and put it in the section, so the reader sees what you looked at. When git in the session directory cannot list the branch's changed files, the gate asks for the picture as well.

The gate checks that the section is there, names a command, and admits no unproven part. Whether the run proves the change stays a judgment for the author and the reviewer.
