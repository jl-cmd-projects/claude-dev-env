# The review loop runs before the merge

A pull request the agent made merges only after a code review of its head comes back clean. Loop it:

1. Review the head with the command `CLAUDE_MERGE_REVIEW_COMMAND` names. Where it is unset, run `/code-review high --max-findings all` against the base.
2. Record the pass: `python3 ~/.claude/scripts/merge_review_receipt.py <owner>/<name> <number> <head sha> <finding count>`.
3. Fix every valid finding, push, and review the new head. Answer each finding you rule out on the pull request with its file:line evidence.
4. Repeat until a pass records `CLEAN`. A pass whose every finding is ruled out records `CLEAN` with `--ruled-out <finding count> --rulings <link to the rulings comment on this pull request>`.
5. Merge pinned to that head: `expectedHeadSha` on the merge tool, or `--match-head-commit` on `gh pr merge`.

`hooks/blocking/merge_review_gate.py` denies any other merge. In a merge-queue repository, enqueue with `gh pr merge <number> --repo <owner>/<name> --auto --match-head-commit <head sha>`; auto-merge that names no head is denied. A repository whose own CI and merge queue review and merge its pull requests is listed in `CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES`, comma separated as `owner/name`, and skips the gate.
