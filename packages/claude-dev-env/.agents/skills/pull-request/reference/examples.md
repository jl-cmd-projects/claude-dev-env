# Pull request examples

Create example: the writer produces `pr-body.md`. The linter exits `0` for
`pr-create`. `pull_request.py create` publishes one ready pull request. The
readback matches the title, body, head SHA, and draft state.

Rejected comment example: the comment body names a worktree file. The linter
returns a non-zero exit. No account lookup or GitHub request runs. Replace the
path with inline text or a permanent artifact URL, then rerun.

Recovery example: one old record remains after an interrupted legacy account
swap. The user selects that exact file and confirms its session is inactive.
The recovery command restores the named account and deletes only that record.
