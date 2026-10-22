# Pull request body sections

A reviewer reads the body in place of the code. The body says what the change does, how it was tested, what could break, and how to undo it. The order follows the Claude Code team's [code review article](https://claude.dev/blog/solving-code-review-at-anthropic/), whose template "asks how the change was tested and how to undo it". The opening sections follow the team's public pull requests, such as [claude-code #69470](https://github.com/anthropics/claude-code/pull/69470), which opens with What this does, Why now and What changed.

| Section | Holds |
|---|---|
| `## What this does` | Two or three plain sentences: the behavior before, the behavior after, and who notices. Written for a reviewer who has not read the worker's conversation. |
| `## What changed` | One bullet per area of the diff, in plain words. |
| `## Existing work` | What already did part of the job, with a link or file and line, and what this change adds. Or the places searched. |
| `## Proof in practice` | Each command in backticks, the output without the change and with it, and anything still unproven. |
| `## Eval` | Only for a `feat` title. The eval's cases and grader, the command, and its result. |
| `## Risk` | What could break, for whom, and how anyone would notice. `Low` and one reason for a doc or test change. |
| `## How to revert` | The exact undo step, and any data or state a plain revert leaves behind. |

A repository's own sections, such as a request record or a session link, follow these. Optional `## Why now` and `## After merge` sections go after What this does and after How to revert.

`pull_request.py template` writes the headings in this order. `durable_post_lint.py` reports a create body missing What this does, Risk, or How to revert, and the proof gate holds one missing Existing work, Proof in practice, or Eval for a `feat` title.
