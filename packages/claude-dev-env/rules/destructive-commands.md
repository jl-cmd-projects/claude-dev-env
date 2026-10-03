# Destructive commands in Bash

**When:** Removing files or writing a destructive command string.

No hook watches Bash commands; a permission prompt can stall unattended work. Keep destructive literals out of command strings, including data. Use literal absolute targets; never target a bare temporary root. Use `git rm` for tracked files. Pass bodies by file and test hooks through the test suite. Copy this line into every subagent prompt:

> Never use bash rm in any form. Delete scratch/probe files with the PowerShell tool (Remove-Item -Recurse -Force -Confirm:$false <absolute path>), or leave them in the OS temp dir; remove worktrees only via git worktree remove --force.

**Enforcement:** none, the agent applies it; the harness may prompt.

**Full text:** [`docs/rule-guides/destructive-commands.md`](../docs/rule-guides/destructive-commands.md). Read it before any removal.
