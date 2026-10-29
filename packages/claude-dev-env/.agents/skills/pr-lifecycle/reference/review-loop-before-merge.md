# The review loop runs before the merge

A pull request the agent made merges only after a code review of its head comes back clean. Loop it:

1. Review the head with the command `CLAUDE_MERGE_REVIEW_COMMAND` names. Where it is unset, run `/code-review high --max-findings all` against the base. This is a full pass.
2. Record the pass: `python3 ~/.claude/scripts/merge_review_receipt.py <owner>/<name> <number> <head sha> <finding count>`.
3. Fix every valid finding, push, and review the new head. Answer each finding you rule out on the pull request with its file:line evidence.
4. The first three passes are full passes. Each later pass is `/code-review low --fix <number>`. It reads only the pull request's diff against its base and leaves its fixes uncommitted. Name the number: after a push, a bare `/code-review low` diffs the branch against its own upstream and sees nothing. Commit and push those fixes, then run the next pass on the new head. A pass that reported findings records its finding count, even when `--fix` fixed them all.
5. Repeat until a pass records `CLEAN`. A pass whose every finding is ruled out records `CLEAN` with `--ruled-out <finding count> --rulings <link to the rulings comment on this pull request>`.
6. Merge pinned to that head: `expectedHeadSha` on the merge tool, or `--match-head-commit` on `gh pr merge`.

A pass run before the pull request opens names `open` in place of the number and the full 40 character head: `python3 ~/.claude/scripts/merge_review_receipt.py <owner>/<name> open <head sha> <finding count>`. A pass whose every finding is ruled out adds `--ruled-out <finding count> --rulings <path:line for each finding, comma separated>`. Run it in the checkout that holds the head. It checks that each `path:line` exists at that head, and each finding needs a different one. A merge pinned to that head passes on an open pass only at zero findings. Rulings for the merge go on the pull request, as in step 5.

`hooks/blocking/merge_review_gate.py` denies any other merge. In a merge-queue repository, enqueue with `gh pr merge <number> --repo <owner>/<name> --auto --match-head-commit <head sha>`; auto-merge that names no head is denied. A repository whose own CI and merge queue review and merge its pull requests is listed in `CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES`, comma separated as `owner/name`, and skips the gate.
