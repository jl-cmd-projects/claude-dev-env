Back to the [rule entry](../../rules/features-start-with-an-eval.md).

# Features start with an eval

**When this applies:** A user asks for a new feature or a change in behavior, in any project.

## What counts

A feature is behavior a user or a caller can see that did not exist before, or that now works differently: a command, a flag, a page, an endpoint, a hook, a rule, a skill, a report, or an integration. A bug fix that restores intended behavior, a rename, a refactor, a docs edit, a question, a test run, and speed work that leaves the output the same are not features.

An eval is three things for one feature: a set of input cases with their expected results, a runner that drives the feature through the entry point its users call, and a grader that scores each output. A test suite counts when it does all three for that feature.

## Rule

1. Make the Skill tool call with skill `claude-api` and args `build-eval` your first action on the ask. A user who types `/claude-api build-eval` has made the same call.
2. Run the existing-work search from [`explore-thoroughly.md`](../../rules/explore-thoroughly.md) next. The guide's own first step also looks for cases, graders, and runners that exist.
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

`hooks/blocking/pull_request_proof.py` reads each new pull request before it opens, through `pr_lifecycle_skill_gate.py`. A new pull request is a `gh pr create` command, a GitHub MCP create call, or a GitHub MCP `run_workflow` dispatch whose inputs name a `head` branch and a `title`, because that workflow opens the pull request. A pull request whose title starts with `feat` (`feat:`, `feat(scope):`, `feat!:`) is denied when:

- its body has no "Eval" heading, or the text under that heading names no command in backticks;
- the session's transcript is readable and shows no `claude-api` Skill call with args `build-eval`, and no `/claude-api build-eval` command.

The gate checks that the section and the call are there. Whether the eval measures the feature stays a judgment for the author and the reviewer. The order of the first action and the separate session for an existing feature are not checked by a hook, so the agent applies them.
