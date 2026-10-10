# Bash dispatchers

This family rewrites a Git Bash command when path conversion would change a revision argument. After shell calls, it can inject a pull request checklist into the agent's context.

## Checks

- `blocking/bash_pre_tool_use_dispatcher.py` combines hosted shell decisions and forwards an updated command when a hosted rewriter allows it.
- `blocking/msys_rev_path_rewriter.py` adds a narrow `MSYS2_ARG_CONV_EXCL` prefix for affected revision and path tokens.
- `blocking/headless_claude_broker_gate.py` denies a headless `claude -p` or `claude --print` call and names the broker command to run instead.
- `blocking/gh_global_account_switch_gate.py` denies `gh auth switch`, `gh auth login`, and `gh auth logout` and names the per-command `GH_TOKEN` form to run instead.
- `blocking/cloud_graphql_gate.py` denies `gh api graphql` and an HTTP client call to `api.github.com/graphql` inside a cloud session, where the proxy answers GraphQL with HTTP 403, and names the REST routes to run instead.
- `blocking/bash_post_call_dispatcher.py` runs hosted observers and joins their context output without blocking the call.
- `advisory/pr_done_reminder.py` adds a pull request checklist after a successful push or pull request creation.

## When it fires

- `blocking/bash_pre_tool_use_dispatcher.py` runs on `PreToolUse`, matcher `Bash`, timeout `60` seconds in `hooks.json`.
- `blocking/msys_rev_path_rewriter.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds. `ALL_BASH_HOSTED_HOOK_ENTRIES` selects the `Bash` tool.
- `blocking/headless_claude_broker_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools.
- `blocking/gh_global_account_switch_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools.
- `blocking/cloud_graphql_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools, when `CLAUDE_CODE_REMOTE` is `true`.
- `blocking/bash_post_call_dispatcher.py` runs on `PostToolUse`, matcher `Bash|PowerShell`, timeout `60` seconds in `hooks.json`.
- `advisory/pr_done_reminder.py` runs inside that dispatcher on `PostToolUse`, matcher `Bash|PowerShell`, timeout `60` seconds. `ALL_BASH_POST_TOOL_USE_HOSTED_HOOK_ENTRIES` selects `Bash` and `PowerShell`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The test fixtures isolate shell payloads.

- **Pre-call dispatch.** Input is a clean Bash command. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_bash_pre_tool_use_dispatcher.py -q`. The adjacent test observes the combined decision and hosted precedence.
- **Revision rewrite.** Input is a Git command with `origin/main:.claude/settings.json`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_msys_rev_path_rewriter.py -q`. The adjacent test observes the `origin/main:` exclusion prefix.
- **Broker gate.** Input is a `claude -p task` command. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_headless_claude_broker_gate.py -q`. The adjacent test observes a denial that names the broker command.
- **Cloud GraphQL gate.** Input is a `gh api graphql` command with `CLAUDE_CODE_REMOTE=true`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_cloud_graphql_gate.py -q`. The adjacent test observes a denial that names the REST routes, and silence outside a cloud session.
- **Post-call dispatch.** Input is a Bash call that yields hosted context. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_bash_post_call_dispatcher.py -q`. The adjacent test observes a joined context payload and exit code zero.
- **Pull request reminder.** Input is a completed push or pull request creation. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_pr_done_reminder.py -q`. The adjacent test checks the reminder trigger and checklist verdict.

## Gotchas

- The pre-call dispatcher stops after a denial. It continues after ask and allow decisions so a later hosted hook can deny.
- The post-call dispatcher runs every hosted observer and passes only context. Its name avoids a substring collision in `bin/install.test.mjs`.
- The post-call roster includes `PowerShell`; the reminder script checks both tool names even though its docstring describes Bash calls.
- `bin/install.mjs` includes folded and retired shell hook paths for registration cleanup.
