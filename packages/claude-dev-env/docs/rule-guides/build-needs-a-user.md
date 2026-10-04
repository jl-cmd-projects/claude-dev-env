# Build needs a user

Full text behind [`rules/build-needs-a-user.md`](../../rules/build-needs-a-user.md), which loads in sessions as the short form.

## First use and size

A caller can be a hook entry, workflow step, skill, command, or module in the same change. First use can be a date or a named event. Prior manual use and frequency show whether the job recurs. An unanswered point leaves the owner a one-line statement of the intended build and the missing answer while the rest of the task continues.

A correction starts as a row in a rule file. [`correction-lens.md`](../../rules/correction-lens.md) describes when repetition warrants a hook or lint. The first implementation needs only the behavior its first caller uses.

## Where the check runs

The staged policy lint's `uncalled-new-file` rule reads newly added code files under `scripts/`, `hooks/`, `bin/`, `ci/`, or `tools/`. It reports a file whose name appears only in its own tests, `CHANGELOG.md`, `README.md`, and `bin/ever-shipped-skills.mjs`. CI runs the lint against the merge base.

The code checks caller references. The other decision points, including first use and prior manual work, depend on the author.

## Why the caller matters

The Codex compatibility watcher shipped 502 lines and 599 lines of tests in July. PR 1488 deleted it in September. Its own test was the only file that named it.

## Sibling rules

| Rule | Role |
|---|---|
| [`prefer-existing-tools.md`](../../rules/prefer-existing-tools.md) | Search before building |
| [`correction-lens.md`](../../rules/correction-lens.md) | A repeated correction moves up a layer |
| [`archiving-agent-config.md`](../../rules/archiving-agent-config.md) | How an unused capability leaves service |
