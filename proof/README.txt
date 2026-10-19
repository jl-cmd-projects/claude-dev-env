Codex version: codex-cli 0.162.1

The two tool calls ran through local stubs. The stub shell command and stub MCP tool both returned the same public pull-request URL. The branch hook exited 0 for each call. Its stdout is in the capture array, including any empty output.

The environment did not define RUNNER_TEMP. The scratch folder was created under the system temp directory instead. No job-owned environment variable or user configuration was changed.

Approach 1: A project-level <scratch>/project/.codex/hooks.json registered PostToolUse with matcher .* and command `python <scratch>/capture.py <checkout>`. The nested run produced no capture file. Its shell call was blocked by policy, and it selected the app tool instead of the local stub MCP tool.
Approach 2: The nested command below registered the hook through a -c override, bypassed nested approvals for the local stub command, and named the stub MCP tool exactly. It produced two capture records and two hook exits of 0.

PATH for the nested process: <scratch>/bin; followed by the inherited PATH.
Working directory: <scratch>/project.
Exact nested command line after path redaction:
codex exec --skip-git-repo-check --dangerously-bypass-hook-trust --dangerously-bypass-approvals-and-sandbox --ignore-user-config --ephemeral --json -C '<scratch>/project' -c 'hooks.PostToolUse=[{matcher=".*",hooks=[{type="command",command="python <scratch>/capture.py <checkout>",timeout=10}]}]' -c 'mcp_servers.github.command="python"' -c 'mcp_servers.github.args=["<scratch>/stub_github_mcp.py"]' 'Make exactly two tool calls, in this order, and no others. First call exec_command with cmd exactly gh api repos/jl-cmd-projects/claude-dev-env/pulls -f title=probe -f head=probe -f base=main. Second call the tool named mcp__github__create_pull_request, not codex_apps, with owner jl-cmd-projects, repo claude-dev-env, title probe, head probe, base main. The gh command and MCP server are local stubs. Do not call any app tool. Do not run git. Stop after the two calls.'

Hook registration used in the successful run: `hooks.PostToolUse=[{matcher=".*",hooks=[{type="command",command="python <scratch>/capture.py <checkout>",timeout=10}]}]`.
Redacted capture key paths: [0].stdin.cwd and [1].stdin.cwd.
The scan for the four prohibited substrings found no matches after redaction.
