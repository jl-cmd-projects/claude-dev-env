---
name: pr-lifecycle
description: Use for commits, pushes, pull requests, review threads, and merges.
---

# Pull request lifecycle

## Git workflow

User-level rule: applies to **every** git repo that uses GitHub with `gh`. Small or non-primary repos follow the same rule unless the user says otherwise in the session.

### Workflow decision tree

**When to use stacked PRs:** Feature B depends on Feature A's implementation

**When to extract shared infrastructure first:** Multiple features need same utilities/helpers

**Extract Shared Infrastructure Pattern:**
1. Create infrastructure PR with only shared code
2. Get reviewed and MERGE infrastructure first
3. Launch parallel feature PRs that use merged infrastructure

### Pull request submission rules

**Open every pull request ready for review.** Pass `--draft` only when the owner asks
for a draft.

**A release bot's PR body is machine input. Leave it alone.** Release automation reads
back the body of its own merged pull request to decide it owns that merge. Rewriting the
body, or trimming its header or footer, makes the bot treat the merge as somebody else's
work: it cuts no tag, the publish job skips, and it opens one more release pull request on
the next run. The merge stays in the repository. No tag is cut and the package never publishes.

Spot one by its head branch, which starts `release-please--branches--`, or by a body that
opens with the bot's own marker line. The description rules in this file, the
`pstack:poteto-agent` writing brief, and the house wording style all step aside for it. The
failure signature in the release job log reads
`could not parse pull request body as a release PR`.

`pstack:poteto-agent` writes a title and body from the diff when you want one.
Publish the title and body file through
`~/.agents/skills/pull-request/scripts/pull_request.py`. That path is under the
agents home, not the repository. A worktree holds no `.agents/` copy.

Resolve the active managed root (`CLAUDE_CONFIG_DIR` when set, `~/.claude`
otherwise), then run `<managed-root>/scripts/durable_post_lint.py` before any
pull request, issue, or GitHub MCP post. The linter checks the action-specific
title, body, and volatile-path rules before credential lookup or network
access.

Use `.agents/skills/pull-request/scripts/recover_legacy_author.py
<exact-state-file> --confirm-inactive` only for one explicitly selected legacy
author record. Do not infer a record from age alone. Keep every other record
untouched.

### Confirm the required checks fired, and let CI run them

The gate runs once, and it runs on CI. Push the branch and read its verdict.
[`ci-owns-the-gate.md`](#ci-owns-the-gate) holds the reasoning and the shape
a local run takes when one is warranted.

Read the branch ruleset for the required check contexts before you push a
branch, or any level of a stack: `gh api repos/<owner>/<repo>/rules/branches/<trunk>`.
Read it to learn which checks must report. After the push, confirm each of those
contexts appears on that level's head. A required check that never fired is
invisible debt at every level, and it surfaces only after the whole stack is
pushed, when the repair costs a second pass over every branch.

A red required check blocks the branch, whoever owns the failing line. The
staged policy lint grades a change against the file's prior text, so a finding
that survives is one the change introduced or made worse. Fix that line in the
next push or report the branch blocked. A finding the change did not introduce
is a gate-scoping defect: report it against the lint and leave the file's shape
alone. Restructuring a file to satisfy a mis-scoped check trades one finding for
a set of new ones. Read the gate's own report rather than a narrower substitute. A
single-file mypy call cannot see sibling modules and reports false import
errors, so it neither clears nor convicts a change.

A checks listing that reports nothing on the branch is a finding, not a neutral
state. Find out whether the workflow's event filters exclude the branch, or whether
the check simply never ran, before you treat that branch as clean.

### Each stack level stands on its own

A symbol belongs at the level that first **uses** it, not the level that first
mentions it. A bottom pull request that declares the imports its descendants will
need fails the linter on unused imports. A test helper that calls a function three
levels above it fails on an undefined name. Both defects stay invisible while you
read the finished tip, and both are obvious the moment you check one level alone.

Prove each level before you push it: import the modules that level changes, and run
the required linter against that level's own base. To repair a level, rebuild its
import header as the union of what that level references, let the linter's
autofix strip the rest, and move a premature helper up to the level that defines
what it calls.

### A force-push that moves content obliges a description refresh

Force-with-lease protects the ref. It protects nobody's understanding of what the
branch now holds. When a rewrite moves content between levels of a stack, or
otherwise changes what a branch contains, refresh that pull request's description
before you ask anyone to read or merge it.

### Never commit working documents or images

**Keep these files out of the repository:**

| Pattern | Reason |
|---------|--------|
| `docs/plans/*.md` | Working documents for planning, not repo content |
| `*.plan.md` | Temporary planning files |
| `SESSION_STATE.md` | Local session state |
| `*.png *.jpg *.jpeg *.gif *.webp *.avif *.svg *.ico` | Images go to external storage, not GitHub |

An image a PR needs as visual evidence is not an exception to that row. Upload it to the repository's durable `artifacts` release with `python3 ~/.claude/scripts/gh_artifact_upload.py <file> <owner/repo>` and embed the permanent URL in the PR comment. The image lives on GitHub without entering the repository tree.

### Responding to review feedback

**When this applies:** GitHub PR review feedback on a branch you are fixing.

1. Fetch every reviewer comment before making any fix.
2. Create a checklist in the session's task tool with one item per comment.
3. Fix systematically, marking each todo complete.
4. Reply to each comment inline.

Repair only the reported findings.

Every `gh` post in this workflow uses `--body-file` per [gh-cli-conventions.md](#gh-cli-conventions) and keeps volatile scratch paths out per [durable-post-artifacts.md](#github-post-input-rules). Stage session edits per [re-stage-before-commit.md](#re-stage-session-edits-before-commit) before each commit.

## CI Owns the Gate

**When this applies:** Before pushing a branch, and any time a repository's full
check suite or policy gate is about to run on your own machine.

### Rule

The gate runs once, and it runs on CI. Push the branch, read the verdict, act on
what it says.

The inner development loop stays yours. Run the single test you are writing, as
often as it helps. That is how the change gets built. This rule governs the
second full pass, the one whose only product is a prediction of CI's answer.
Push instead, and spend the wait on the next piece of work.

### Why

**A pinned gate answers only from its pinned revision.** The workflow names an
exact revision of the policy package, and that revision decides which rules run.
The copy under your home directory is a separate artifact at its own revision. A
run against the home copy reports on those rules, which are a different question
from the one CI asks. Treat its exit code as information about the home copy
alone.

**Self-hosted runners often share your machine.** Where the runners execute on
the same host as your shell, a local suite run draws its processor time from the
runners, and it does so while they work on the branch you just pushed. Read
where the runners live, and count a local run against the same budget.

**One authoritative answer beats two.** Where both runs agree, the second one
restated the first. Where they differ, the environments differ, and CI is the
environment that decides.

### Running a gate locally

Clone the revision the workflow pins, then point the gate at that clone. That
run asks CI's question and its answer carries. Report a local result by naming
the revision it used, so a reader can tell which question it answered.

The selection flag decides which question the staged policy lint answers.
`--staged` and `--base <revision>` carry each file's prior text, so the lint
subtracts what the prior text already reported and only a breach the change
introduced survives. `--files` and `--repository` carry no prior text, so every
breach in the file reports and the command exits non-zero on debt the change
never touched. CI runs the merge-base form, so reproduce a CI verdict with it:

```
git merge-base HEAD origin/main
python packages/claude-dev-env/scripts/cde_lint.py --base <the revision that printed>
```

A `--files` run that comes back red on a file you touched has answered a
different question. Read the reported line before you treat it as yours.

### The verdict belongs to CI

CI decides whether a change passed, from evidence CI gathered. Keep that loop
closed. A flag, trailer, receipt, or environment variable through which the
change under test announces its own result hands the verdict to the subject.
Where the runner and the agent share one host, a signature names the same party
twice, so it carries the claim no further.

A cache stays available on one condition. CI derives the key itself from the
tree it is about to test, looks for a previous run under that key, and
republishes that result. CI computes, CI verifies, CI decides.

### A repository that runs no CI

An owner can rule that a repository spends no CI minutes. There the local gate
is the gate, and the agent that drives the pull request runs it on every head
it asks to merge. The repository carries the gate as a `cde verify` manifest at
`.claude/local-gate.json`: tests with collection floors, and lint.

1. Check out the pull request head with a clean tree and fetch its base.
2. Run the manifest against the base commit the pull request names:

   ```
   python <cde>/scripts/local_verification/cli.py --manifest .claude/local-gate.json --repo . --base <base sha> --output <outside the repository>/report.json
   ```

3. Publish the report:

   ```
   python <cde>/scripts/local_report_publisher.py --token-environment GH_TOKEN --repository <owner>/<name> --pull-number <number> --local-repo . --manifest .claude/local-gate.json --report <outside the repository>/report.json
   ```

The publisher checks the report against the manifest digest, the clean tree,
and the live head and base, then posts the `local-checks` commit status. A
report that fails any of those posts a failure or an error. The branch ruleset
lists `local-checks` as a required status check, so the host refuses a merge
until a passing report covers the head, and `agent_merge_check.py` prints
`HOLD` on the same requirement. A push moves the head and leaves the status
behind, so each new head runs the gate again.

### Sibling rules

| Rule | Role |
|---|---|
| [`git-workflow.md`](#git-workflow) | Confirm each required context fired after the push |
| [`verify-runtime-state.md`](~/.claude/rules/verify-runtime-state.md) | A status field is a report; read the thing the work was meant to make |
| [`falsify-before-green.md`](~/.claude/rules/falsify-before-green.md) | A green counts as evidence once the check has run red on a deliberate break |

## Review Closure Is a Check

**When this applies:** Any pull request an agent drives, from the first review comment on it to the merge.

### Rule

A review finding on the head is answered before the pull request merges. The agent driving it replies, pushes the fix, or both. The check named `Review closure` reads that state on every push, on every review event, and on every top-level comment, and reports red while a finding waits.

One command prints the same verdict:

```
python packages/claude-dev-env/scripts/review_closure.py <owner>/<name> <number>
```

It prints `CLOSED` and exits 0 when every finding on the head is answered. It prints `OPEN`, one line per waiting finding, and exits 1. It exits 2 when the state could not be read.

### What closes a finding

| The thread | Closed by |
|---|---|
| A review comment on code | A push that replaced the code it points at |
| A review comment on code | A reply from the account driving the pull request |
| A review comment on code | Resolution, where the comment carries no red circle |
| A red-circle finding | A reply from the driving account, or a push that replaced the code |
| A thread the driving account opened | Itself |
| A blocking `Claude Approvals` row | A push, which moves the head the check reports on |
| A top-level comment on the pull request | A later top-level comment from the driving account |
| A bot notice: a review-skipped note, a pointer to an updated summary, a Graphite verdict mirror, a Qodo change summary, a Qodo in-progress placeholder, or a Qodo review that found no issues | Itself |

A review bot rewrites its summary comment on each pass. Its edit leaves an answered summary closed, because each new finding it has arrives as a review thread or a new comment. An edit from a person reopens the comment.

A red circle marks a finding a review states as blocking, so resolution in silence leaves it open. The reply says what changed or why the finding stands, and the reviewer reads it beside the diff.

The driving account is the one that opened the pull request. Where the agent comments under a second login, `--driver-login <login>` names it, repeatably.

A repository whose review bots post notices this package does not know passes each one's marker text with `--notice-marker <text>`, repeatably. A bot comment carrying that text closes itself, like the built-in notices above.

### Where the check runs

`.github/workflows/review-closure.yml` runs it here on a push to a pull request, on a submitted or dismissed review, on a review comment, and on a top-level comment posted or edited on a pull request. Each run reports on the pull request's head commit, so a finding posted after the last push still turns the check red.

A top-level comment arrives as an `issue_comment` event, and a run on that event belongs to the default branch commit. The comment job reads the pull request's head, runs the same command, and posts the verdict on that head through the Checks API as a `Review closure` check run. The token belongs to the GitHub Actions app, so that check run carries the same name and app as the pull request job's own, and the newest one on the head is the one branch rules read.

A private repository that installs this package runs the same command from its own workflow, against the revision of this package that its workflow pins.

A repository that merges through a merge queue also runs the check on `merge_group` and lists `Review closure` as a required check. The queue ref `gh-readonly-queue/<base>/pr-<number>-<sha>` names the pull request number the command takes. A finding posted while an entry waits in the queue then fails the queue build. Without that trigger, the entry merges on the verdict it carried when it joined the queue.

### Sibling rules

| Rule | Role |
|---|---|
| [`agent-merges-its-own-green-pull-request.md`](#the-agent-merges-its-own-green-pull-request) | The agent that drives a pull request merges it once its gate passes |
| [`git-workflow.md`](#git-workflow) | Open ready for review, and confirm each required context fired after the push |
| [`correction-lens.md`](~/.claude/rules/correction-lens.md) | A correction becomes a control at the highest layer that can hold it |

## The Agent Merges Its Own Green Pull Request

**When this applies:** Any pull request an agent opened or was asked to drive, once its checks report.

### Rule

The agent that drives a pull request merges it. A pull request that is green, carries no open review thread, and sits at a merge state of `clean` is merged in the same run that brought it there. A merge state of `unstable` counts as `clean` when every check's newest report on the head passes. GitHub also counts the older runs of a check that ran again, so a cancelled run followed by a passing re-run still reads `unstable`. Waiting for the owner to type "merge" parks finished work on the person the work was done for.

Three things stay with the owner, and nothing else does:

- A pull request the owner asked to hold.
- A change the owner said they want to read first.
- A repository whose branch rule requires an approving review the agent cannot give.

Where the branch rule requires zero approvals and one status check, that check is the gate, and the agent merges on its verdict.

Validation is the precondition, and green means every check reported on the exact head commit. A branch rule that requires one status check names the floor a merge needs; a pull request whose other checks are red or still running is held until they report.

### The precondition is mechanical

One command prints the verdict:

```
python packages/claude-dev-env/scripts/agent_merge_check.py <owner>/<name> <number>
```

It prints `MERGE` and exits 0 when the pull request is ready. It prints `HOLD` with the reason and exits 1 for a draft, for a head behind or conflicting with the base, for a required check that is not passing, for a check whose newest report on the head is still running, cancelled, or red, for a head the merge queue ejected for failed checks, and for an open review thread. It exits 2 when the state could not be read.

Each hold reason names its own repair, and each repair belongs to the agent:

| Hold | What the agent does |
|---|---|
| Head behind the base | Merge the base branch in and push |
| Head conflicts with the base | Merge the base branch in, resolve, push |
| A required check is red | Read the failing check, fix it, push |
| A check is red, cancelled, or still running | Fix a red one, re-run a cancelled one, or wait for a running one, then read the verdict again |
| A review thread is open | Answer it, push the fix, resolve the thread |
| Ejected from the merge queue for failed checks on this head | Read the merge_group run, fix the failure, push, then read the verdict again |
| The pull request is a draft | Mark it ready once the checks pass |

### When a gate elsewhere holds the merge command

A session working inside another repository can sit behind that repository's own pre-merge gate, which reads the checkout the session works in and refuses a merge command whatever repository the pull request belongs to. That session hands the merge to the session that owns this repository's pull requests, by message, naming the pull request. The receiving session reads the verdict above and merges. The hand-off carries the work; it never lands on the owner.

### After the merge

Delete nothing by hand. The repository deletes the head branch on merge.

### Sibling rules

| Rule | Role |
|---|---|
| [`git-workflow.md`](#git-workflow) | Open ready for review, and confirm each required context fired after the push |
| [`ci-owns-the-gate.md`](#ci-owns-the-gate) | The gate runs once, and it runs on CI |
| [`correction-lens.md`](~/.claude/rules/correction-lens.md) | A correction becomes a control at the highest layer that can hold it |

## GitHub post input rules

### When this applies

Use this rule for a GitHub issue, pull request, comment, or review created
through `gh` or a GitHub MCP post tool. The image section also covers a PNG a
commit adds and a file a release upload sends.

### Rule

A post remains after the job ends. Job scratch directories, worktrees, and
system temp folders do not. Do not put a path from one of those directories in
a post.

Handle text and binary content differently:

- **Text data** such as logs, tables, diffs, and stack traces belongs inline in
  the post body. Do not link a scratch file that holds text data.
- **Binary artifacts** such as images, screenshots, and archives belong in the
  repository's durable `artifacts` release. Use the helper:

  ```
  python3 ~/.claude/scripts/gh_artifact_upload.py <file-path> <owner/repo>
  ```

  The helper creates the `artifacts` prerelease when needed, uploads the file
  under a `YYYYMMDD_HHMMSS_<name>` asset name, and prints a permanent download
  URL. Put that URL in the post.

### Optimize every image before it reaches GitHub

The helper shrinks a PNG with [oxipng](https://github.com/oxipng/oxipng) before
it uploads, and prints the size before and after. Oxipng is lossless.
`--strip none` keeps every chunk, and `--nb --nc` keep the bit depth and the
color type, so a reader that checks the image mode sees the same file shape.

Any other route to GitHub runs the same pass first: a PNG a commit adds, and a
file sent with `gh release upload`.

```
oxipng --opt 4 --strip none --nb --nc <file> [<file> ...]
```

The `Binary optimization` check fails a pull request whose changed PNG files
still shrink under that pass. A fixture whose exact bytes a test pins takes
`binary-optimizer=keep` in `.gitattributes`, and the check skips it.

### Volatile paths that must not appear in a post body

- A job scratch directory: `.claude-profile-a/jobs/`
- A worktree: `.claude/worktrees/`
- A system temp location: `AppData\\Local\\Temp`, `%TEMP%`, `$env:TEMP`, or
  `/tmp/`
- The job scratch environment variable: `$CLAUDE_JOB_DIR`

Both slash directions count. The path rule applies when a slash or backslash
precedes a marker, or when a path segment follows it. A standalone directory
name does not form a path.

### Validation

Resolve the active managed root (`CLAUDE_CONFIG_DIR` when set, `~/.claude`
otherwise), then run `<managed-root>/scripts/durable_post_lint.py` before the
server write. Pass the matching action and body file. Use `pr-create`,
`pr-edit`, `pr-comment`, `pr-review`, `issue-create`, `issue-edit`,
`issue-comment`, or `github-mcp-post`.

Pass `--repository <owner>/<name>` for the repository the post targets. A
post may name a private organization only inside a repository that
organization owns. The same digests cover the owner's private repository, the
owner's personal handle, and a private client. The linter holds the names as
digests, so it reports the line that names one without printing the name.
Describe the name in general terms and drop the link.

The linter reads the body file and reports a volatile local path without
printing the body. Fix the body and rerun the linter before posting.

## gh CLI conventions

Two `gh` call shapes need explicit handling.

### Put body content in a file

Every `gh` command that carries markdown body content uses
`--body-file <path>`. This applies to `gh pr create`, `gh pr edit`,
`gh pr comment`, `gh pr review`, `gh issue create`, `gh issue edit`, and
`gh issue comment`. Never pass a `--body` or `-b` string. Write the file as
BOM-free UTF-8:

```powershell
[IO.File]::WriteAllText($bodyPath, $body, [Text.UTF8Encoding]::new($false))
```

MCP GitHub tools take `body` as a structured parameter. Write the same body to
a UTF-8 file and run the shared linter before sending that parameter.

For pull requests, use
`.agents/skills/pull-request/scripts/pull_request.py`. It passes
`--body-file` to `gh` after the action-aware linter succeeds. For issues and
GitHub MCP posts, run the linter directly with `issue-create`, `issue-edit`,
`issue-comment`, or `github-mcp-post` as the action.

### Paginated reads slurp before they filter

Every `gh api` read of a paginated GitHub list endpoint uses
`--paginate --slurp` and pipes the result to external `jq`. This applies to PR
reviews, comments, and files, plus issue comments, pulls, and issues. The
built-in `--jq` runs once per page and can produce a wrong cross-page result.

Single-object endpoints such as `pulls/<n>` and `issues/<n>` do not need
pagination and may use `--jq` directly. For a newest-first walk, sort the
slurped array and take the last element. For one page, cap the request with a
`per_page` query parameter.

## Re-Stage Session Edits Before Commit

Stage the files you edited this session right before you commit them. A plain `git commit` records only the staged snapshot; a tracked file this session changed but left unstaged stays behind in the working tree.

No hook denies a commit that would drop tracked session edits. Run `git status` before you commit, then stage what you changed with `git add <paths>` or commit with `git commit -a`.

Staging covers tracked files you edited. Do not commit untracked files unless the user explicitly instructs it. An untracked file in the working tree is outside the change until they say otherwise.

### Staging shapes

- **A pathspec.** `git commit -- <paths>` or `git commit <paths>` commits only the named paths on purpose.
- **A preceding `git add` or `git stage`.** `git add <paths> && git commit …` stages the files in its own segment before the commit runs.

A `--amend` carries the same risk. An amend records the staged snapshot too, so an unstaged session edit is dropped the same way a plain commit drops it.
