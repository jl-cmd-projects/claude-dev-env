Back to the [rules index](../../rules/index.md).

# Features start with an eval

## In brief

The DeepStack reproducible-check leaf calls this guide when the work is a new feature or a change in behavior. Only the forced position as the very first action is retired. A reproducible, re-runnable check is still required before any done claim. Red before the fix, the wrong twin fails, and undo fails again. Build the feature against that eval. When the work touches an existing feature with no eval, start a separate session to build that eval in parallel. An Agent-tool subagent does not count. You own its result.

An eval is for a change to agent behavior: a feature that changes a file agents read or load. A feature in plain code is measured by its tests and its proof tier, as [proof-before-pull-request.md](proof-before-pull-request.md) describes.

**Enforcement:** `hooks/blocking/build_eval_before_eval_write_gate.py` denies a write to an eval file before the build-eval call. `hooks/blocking/pr_lifecycle_skill_gate.py` denies a `feat` pull request that changes an agent surface, or whose changed files it cannot read, when it has no "Eval" section or no build-eval call.

**When this applies:** A user asks for a new feature or a change in behavior that changes an agent surface, in any project.

## What counts

A feature is behavior a user or a caller can see that did not exist before, or that now works differently: a command, a flag, a page, an endpoint, a hook, a rule, a skill, a report, or an integration. A bug fix that restores intended behavior, a rename, a refactor, a docs edit, a question, a test run, and speed work that leaves the output the same are not features.

An agent surface is a file agents read as instructions or load as settings: a `SKILL.md`, `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `copilot-instructions.md`, `hooks.json`, `.mcp.json` or `settings*.json` file, or a file under a `skills`, `rules`, `agents`, `commands`, `system-prompts` or `output-styles` folder. Names match in any case, so `Skills/x/skill.md` counts. A feature that changes one owes an eval. Another feature owes its tests.

An eval is three things for one feature: a set of input cases with their expected results, a runner that drives the feature through the entry point its users call, and a grader that scores each output. A test suite counts when it does all three for that feature.

## Rule

For a feature that changes an agent surface:

1. Call the Skill tool with skill `claude-api` and args `build-eval` before the change. A user who types `/claude-api build-eval` has made the same call. A reproducible, re-runnable check is still required before any done claim. Red before the fix, the wrong twin fails, and undo fails again. Only the forced position as the very first action is retired.
2. Run the existing-work search from [`explore-thoroughly.md`](explore-thoroughly.md) next. The guide's own first step also looks for cases, graders, and runners that exist.
3. Follow the guide the skill loads. It asks the user to approve the inputs and the grading method, and to approve the cost before the first paid run. Ask through the session's question tool. Where the host says to keep working while a question waits, continue on the option you recommended and change course if the answer differs.
4. Run the eval before the change to get a baseline, build the feature, and run it again.
5. Give the pull request an "Eval" section. Name the cases and the grader, give the command that runs the eval in backticks, and quote the baseline and the result.

## An existing feature with no eval

When your work touches an existing feature, look for its eval. When it has none, start a separate session that builds it, and keep doing your own work while that session runs. Your own feature still starts with its own eval.

- In a Claude project thread, call `send_message` with the coordinator's session id from `get_channel_session_id`, and ask it to start a thread for the eval. A thread session has no `start_thread_session`, so the coordinator starts that thread.
- In a project's coordinator session, call `start_thread_session` with the brief.
- In a command-line session, start a headless session through the account broker: `python ~/.claude/scripts/account_broker.py run --product claude --report <report.json> -- claude -p "<brief>" --model <model> --effort <level>`.

The brief names the feature, its entry point, and the first step, the `claude-api` skill with args `build-eval`. An Agent-tool subagent is not a separate session. It shares your context window and ends with your turn.

You own that session's result. Check its pull request, and link it from your own pull request's "Eval" section.

## Enforcement

`hooks/blocking/pull_request_proof.py` reads each new pull request before it opens, through `pr_lifecycle_skill_gate.py`. A new pull request is a `gh pr create` command, a `pull_request.py create` command, any other create spelling `followup_pr_dedupe.py` reads (such as `gh pr new` or `gh -R <owner/name> pr create`), a GitHub MCP create call, or a GitHub MCP `run_workflow` dispatch whose inputs name a `head` branch and a `title`, because that workflow opens the pull request. A pull request whose title starts with `feat` (`feat:`, `feat(scope):`, `feat!:`) owes an eval when a path it changes is an agent surface, or when the gate cannot read the list of changed paths. The gate reads that list as the proof tier does: git in a checkout of the named repository, else the GitHub compare API. Such a pull request is denied when:

- its body has no "Eval" heading, or the text under that heading names no command in backticks;
- the session's transcript is readable and shows no `claude-api` Skill call with args `build-eval`, and no `/claude-api build-eval` command. A scan the gate's 20 s deadline stops counts as none shown, and that deny says to call build-eval again.

Each deny names the first agent-surface path, or says the list could not be read. A body with an "Eval" section, or a transcript with the build-eval call, passes that check with no read of the changed paths. The `pull_request.py template` action asks the gate the same question for the current checkout, and adds the "Eval" heading for a `feat` title only when the answer owes one.

`hooks/blocking/build_eval_before_eval_write_gate.py` runs before each Write, Edit, MultiEdit, NotebookEdit, and apply_patch call. It denies a write to an eval file while the session's readable transcript shows no build-eval call. Its transcript scan reads the clock before each block and each line, and stops at the first such read after 5 s, so a line already being parsed finishes first. The registered timeout in `hooks.json` is 10 s. A scan ended by that stop, or by a line over 16 MiB, counts as no call shown, and that deny says to call build-eval again. An eval file sits under an `eval`, `evals`, or `hillclimb` folder, or has a file name that starts with `eval` or `evals` before a separator, such as `eval_runner.py`, or carries `.eval.` or `.evals.`, such as `search.eval.json`. Only a Skill call named exactly `claude-api` counts; a plugin-prefixed name such as `plugin:claude-api` does not.

The gate checks that the section and the call are there. Whether the eval measures the feature stays a judgment for the author and the reviewer. Edits outside eval files before the build-eval call and the separate session for an existing feature are not checked by a hook, so the agent applies them.
