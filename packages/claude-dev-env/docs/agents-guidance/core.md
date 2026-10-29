# Core rules

**When this applies:** Every reply and every file edit, in every session and every host.

## Replies

- **Status.** Changed / proof / blocked.
- **Diffs.** Show the hunk. No prose stand-in.
- **Verdicts.** One line. Read files first. Quote file:line. Code beats brief. No flip-flops.

## Edits

- **Writes.** Write/Edit only. LF. After: git diff --check, file <path>. ASCII unless the file already isn't.
- **Edit gate.** Own worktree. Path overlap with another session -> stop. Behind origin/main -> rebase or report.
- **Scope.** Min diff. No drive-by reformat. No blanket autofix without tests and revert on break.
