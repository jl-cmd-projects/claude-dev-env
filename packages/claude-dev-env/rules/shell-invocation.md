# Shell invocation

**When:** Issuing a Bash-tool shell command, or writing a `settings.json` permission rule.

On Windows, run shell work through `pwsh`: `pwsh -NoProfile -File '<script>.ps1' <args>` for a script, and `pwsh -NoProfile -Command "..."` or the `PowerShell` tool for inline work. A direct interpreter call such as `python script.py` conforms as written. Keep `powershell`, `cmd /c`, and `bash -c` out of permission rules. Keep `$(...)`, unescaped backticks, and `<(...)` or `>(...)` out of Bash commands; split the call or use a flag form such as `git -C "<path>"`. Arithmetic `$((...))` passes.

**Enforcement:** none, the agent applies it; a permission prompt on a wrapped command is the signal. `blocking/msys_rev_path_rewriter.py` only rewrites a `<rev>:<path>` argument.

**Full text:** [`docs/rule-guides/shell-invocation.md`](../docs/rule-guides/shell-invocation.md). Read it before writing a permission rule or a multi-step shell command.
