Back to the [rule entry](../../rules/shell-invocation.md).

# Shell Invocation

Two constraints govern every shell command an agent issues: which shell runs it, and what the command string may contain.

## Use pwsh

Every Bash-tool shell command on Windows uses `pwsh`: `pwsh -NoProfile -File '<script>.ps1' <args>` for scripts, `pwsh -NoProfile -Command "..."` (or a literal `@'...'@` here-string) for inline work, or the built-in `PowerShell` tool for pure-PowerShell workflows (it supports `run_in_background`). Never wrap a script path in `-Command "& '...'"`. The `-File` form keeps `permissions.allow` matching. The `&` call operator is fine for invoking an executable at a path (`& '<venv>\Scripts\python.exe' script.py`).

The mandate covers the shell a command runs through. A direct interpreter invocation, such as a `python` call on a repo script, conforms as written.

Keep `powershell`, `powershell.exe`, `cmd /c`, and `bash -c` out of the `settings.json` permission rules. `Audit-ShellPolicy.ps1` reports those forms and `Migrate-ShellPolicy.ps1` rewrites them to `pwsh`. Both ship in the claude-dev-env repo at `packages/claude-dev-env/scripts/` and run on demand. No hook runs them.

## No shell substitution

No `$(...)`, unescaped backticks, or `<(...)` / `>(...)` process substitution in Bash tool commands. The allowlist matcher reads the raw command string, so a substitution wrapper forces a permission prompt even when every inner segment is auto-allowed. Split into separate tool calls, or use flag forms like `git -C "<path>" rev-parse HEAD`. Arithmetic `$((...))` passes: it spawns no subshell.

When a script file's literal body needs `$(...)`, author it with the Write tool.

## Enforcement

No PreToolUse hook denies a Bash command for its shell form. The substitution constraint above is guidance a reader follows, and a permission prompt on a wrapped command is the signal that one slipped through.

`blocking/msys_rev_path_rewriter.py` only rewrites a Bash command. It keeps Git Bash from converting a `<rev>:<path>` argument when the revision holds a slash. A test pins the dispatcher roster to this one hook.
