# The review loop runs before the merge

A pull request the agent made gets three full review passes with fixes, then merges. Loop it:

1. Review the head with the command `CLAUDE_MERGE_REVIEW_COMMAND` names. Where it is unset, run `/code-review high --max-findings all` against the base. This is a full pass.
2. Record the pass: `python3 ~/.claude/scripts/merge_review_receipt.py <owner>/<name> <number> <head sha> <finding count>`. The receipt counts the pass. Each new head is the next pass, and recording the same head again keeps its pass.
3. Fix every valid finding, push, and review the new head. Answer each finding you rule out on the pull request with its file:line evidence.
4. Passes 1, 2 and 3 are full passes, and each finding they report is fixed in this pull request. After the third pass's fixes, review the new head with `/code-review low <number>`. It reads only the pull request's diff against its base. Name the number: after a push, a bare `/code-review low` diffs the branch against its own upstream and sees nothing.
5. A pass that records `CLEAN` ends the loop. A pass whose every finding is ruled out records `CLEAN` with `--ruled-out <finding count> --rulings <link to the rulings comment on this pull request>`.
6. When pass 4 or a later pass still reports findings, do not loop again. File one issue in the same repository that lists them, push no fix for them in this pull request, and record the pass again with `--filed <issue url>`. It prints `FILED`. Findings you rule out on that pass add `--ruled-out` and `--rulings` as in step 5 and stay out of the issue. Before pass 4, `--filed` is refused.
7. A security finding is the exception. Fix it in this pull request or rule it out with evidence, in any pass, and never file it. A fix pushes a new head, which gets its own pass.
8. Merge pinned to the head of the `CLEAN` or `FILED` pass: `expectedHeadSha` on the merge tool, or `--match-head-commit` on `gh pr merge`.

A pass run before the pull request opens names `open` in place of the number and the full 40 character head: `python3 ~/.claude/scripts/merge_review_receipt.py <owner>/<name> open <head sha> <finding count>`. A pass whose every finding is ruled out adds `--ruled-out <finding count> --rulings <path:line for each finding, comma separated>`. Run it in the checkout that holds the head. It checks that each `path:line` exists at that head, and each finding needs a different one. A merge pinned to that head passes on an open pass only at zero findings. Rulings for the merge go on the pull request, as in step 5. An open pass does not take `--filed` and does not count toward the three full passes.

`hooks/blocking/merge_review_gate.py` denies any other merge. In a merge-queue repository, enqueue with `gh pr merge <number> --repo <owner>/<name> --auto --match-head-commit <head sha>`; auto-merge that names no head is denied. A repository whose own CI and merge queue review and merge its pull requests is listed in `CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES`, comma separated as `owner/name`, and skips the gate.
