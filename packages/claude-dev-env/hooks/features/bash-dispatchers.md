# Bash dispatchers

This family rewrites a Git Bash command when path conversion would change a revision argument. After shell calls, it can inject a pull request checklist into the agent's context.

## Checks

- `blocking/bash_pre_tool_use_dispatcher.py` combines hosted shell decisions and forwards an updated command when a hosted rewriter allows it.
- `blocking/msys_rev_path_rewriter.py` adds a narrow `MSYS2_ARG_CONV_EXCL` prefix for affected revision and path tokens.
- `blocking/headless_claude_broker_gate.py` denies a headless `claude -p` or `claude --print` call and names the broker command to run instead.
- `blocking/gh_global_account_switch_gate.py` denies `gh auth switch`, `gh auth login`, and `gh auth logout` and names the per-command `GH_TOKEN` form to run instead.
- `blocking/cloud_graphql_gate.py` denies the `gh` commands that call GraphQL (`gh api graphql` with any flags before the endpoint, `gh pr`, `gh issue`, `gh project` and `gh discussion` except `gh pr diff` and `gh pr list --web`, `gh status`, `gh org list`, `gh release list`, `gh release view` with a tag, `gh workflow run` without `--ref`, and a few `repo`, `label`, `search`, `ruleset` and `gist` commands, read past `if`, `!` and command substitutions) and an HTTP client or `python -c` style call to `api.github.com/graphql`, with or without a port, inside a cloud session, where the proxy answers GraphQL with HTTP 403, and names the REST routes to run instead.
- `blocking/python_windows_invocation_gate.py` denies, on a Windows host, `python`, `python3` or `py` run with `-I` and without `-X utf8`, because `-I` ignores `PYTHONUTF8` and non-ASCII output then stops with `UnicodeEncodeError: 'charmap'`. Under the PowerShell tool it also denies a `python -c "..."` argument that holds `\"`, because PowerShell ends the string at that quote, and names a script file or a single-quoted here-string to use instead.
- `blocking/transcript_root_search_gate.py` denies a recursive walk or content search that starts at a Claude transcript root, a `projects` folder directly under `.claude`, `.claude-<name>` or `.claude-profiles/<profile>`, with no project folder after it, or with a bare `*` or `**` segment that descends into every project folder. It reads `find`, `grep -r`, `rg`, `ls -R`, `Get-ChildItem -Recurse` or `-Depth`, `Select-String`, and the Grep and Glob tools, and expands variables the command assigns, such as `$p="..."`. A one-level name listing, such as `Get-ChildItem <root> -Directory -Filter "*id*"`, passes. The deny reason names the fix: list the project folders by name, then read the one transcript.
- `blocking/bash_post_call_dispatcher.py` runs hosted observers and joins their context output without blocking the call.
- `advisory/pr_done_reminder.py` adds a pull request checklist after a successful push or pull request creation.
- `advisory/owned_pr_review_loop.py` adds review-loop instructions after the agent opens a pull request on an owned repository outside the preset list of repositories that run their own automated review: run efficient-review until clean, mark the pull request ready, babysit it, and ship it to merge. It also records the pull request for the session in `owned_pr_session_record.py`.
- `blocking/owned_pr_merge_stop_gate.py` holds the end of a turn while a recorded pull request reads open on GitHub and the closing reply has no `Blocked:` line that names it. A failed state lookup passes.

## When it fires

- `blocking/bash_pre_tool_use_dispatcher.py` runs on `PreToolUse`, matcher `Bash`, timeout `60` seconds in `hooks.json`.
- `blocking/msys_rev_path_rewriter.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds. `ALL_BASH_HOSTED_HOOK_ENTRIES` selects the `Bash` tool.
- `blocking/headless_claude_broker_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools.
- `blocking/gh_global_account_switch_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools.
- `blocking/cloud_graphql_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools, when `CLAUDE_CODE_REMOTE` is `true`.
- `blocking/python_windows_invocation_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools. The `-I` check runs only when `os.name` is `nt`.
- `blocking/transcript_root_search_gate.py` runs inside that dispatcher on `PreToolUse`, matcher `Bash`, timeout `60` seconds, for the Bash and PowerShell tools, and on its own on `PreToolUse`, matcher `Grep|Glob`, timeout `10` seconds in `hooks.json`.
- `blocking/bash_post_call_dispatcher.py` runs on `PostToolUse`, matcher `Bash|PowerShell`, timeout `60` seconds in `hooks.json`.
- `advisory/pr_done_reminder.py` runs inside that dispatcher on `PostToolUse`, matcher `Bash|PowerShell`, timeout `60` seconds. `ALL_BASH_POST_TOOL_USE_HOSTED_HOOK_ENTRIES` selects `Bash` and `PowerShell`.
- `advisory/owned_pr_review_loop.py` runs on `PostToolUse`, matcher `Bash|PowerShell|exec_command|shell_command|mcp__.*__(create_pull_request|github_create_pull_request)`, timeout `10` seconds in `hooks.json`. It wakes on `gh pr create`, `gh pr new`, a POST to `gh api repos/<owner>/<repo>/pulls`, a `pull_request.py create` call to the pull request publisher, and an MCP pull request creation. The installer also registers it on Codex `PostToolUse` through `ALL_CODEX_NATIVE_POST_TOOL_USE_HOOK_SCRIPT_NAMES`.
- `blocking/owned_pr_merge_stop_gate.py` runs on `Stop`, timeout `60` seconds in `hooks.json`. The installer also registers it on Codex `Stop` through `ALL_CODEX_NATIVE_STOP_HOOK_SCRIPT_NAMES`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The test fixtures isolate shell payloads.

- **Pre-call dispatch.** Input is a clean Bash command. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_bash_pre_tool_use_dispatcher.py -q`. The adjacent test observes the combined decision and hosted precedence.
- **Revision rewrite.** Input is a Git command with `origin/main:.claude/settings.json`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_msys_rev_path_rewriter.py -q`. The adjacent test observes the `origin/main:` exclusion prefix.
- **Broker gate.** Input is a `claude -p task` command. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_headless_claude_broker_gate.py -q`. The adjacent test observes a denial that names the broker command.
- **Cloud GraphQL gate.** Input is a `gh api graphql` command with `CLAUDE_CODE_REMOTE=true`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_cloud_graphql_gate.py -q`. The adjacent test observes a denial that names the REST routes, and silence outside a cloud session.
- **Python Windows invocation gate.** Input is `python -I s.py` on Windows, and a PowerShell `python -c "print(\"x\")"`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_python_windows_invocation_gate.py -q`. The adjacent test observes a denial that names `-X utf8` or the here-string, and a pass for `-IX utf8`, `-I -X utf8`, and the Bash tool.
- **Transcript root search gate.** Input is `Get-ChildItem $p -Recurse -File -Filter *.jsonl` with `$p` bound to `C:/Users/dev/.claude-profiles/work/projects`, and a Grep call whose path is `C:/Users/dev/.claude/projects`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_transcript_root_search_gate.py -q`. The adjacent test observes a denial that names the list-then-read fix, and a pass for `Get-ChildItem $p -Directory -Filter "*01WUQeBG*"` and a walk inside one project folder.
- **Post-call dispatch.** Input is a Bash call that yields hosted context. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_bash_post_call_dispatcher.py -q`. The adjacent test observes a joined context payload and exit code zero.
- **Pull request reminder.** Input is a completed push or pull request creation. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_pr_done_reminder.py -q`. The adjacent test checks the reminder trigger and checklist verdict.
- **Owned pull request review loop.** Input is a pull request creation result on an owned repository. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_owned_pr_review_loop.py -q`. The adjacent test observes the review-loop block for owned repositories and silence for the preset and foreign repositories.
- **Owned pull request merge gate.** Input is a `session_record_path` file that lists `jl-cmd/snake-game#9` and a `gh` stub that reports `open`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_owned_pr_merge_stop_gate.py packages/claude-dev-env/hooks/test_owned_pr_session_record.py -q`. The adjacent test observes a `block` decision that names the pull request; `closed` and a `Blocked: jl-cmd/snake-game#9 - ...` line pass.

## Gotchas

- The pre-call dispatcher stops after a denial. It continues after ask and allow decisions so a later hosted hook can deny.
- The post-call dispatcher runs every hosted observer and passes only context. Its name avoids a substring collision in `bin/install.test.mjs`.
- The post-call roster includes `PowerShell`; the reminder script checks both tool names even though its docstring describes Bash calls.
- `bin/install.mjs` includes folded and retired shell hook paths for registration cleanup.
