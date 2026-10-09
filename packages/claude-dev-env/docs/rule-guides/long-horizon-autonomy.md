# Long-horizon autonomy

Full text behind [`rules/long-horizon-autonomy.md`](../../rules/long-horizon-autonomy.md).

Source: [Anthropic prompting guidance for Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5).

## Act on what you have

Facts already settled in the conversation remain settled. A recommendation gives the user one course to evaluate. A list of discarded options adds reading without changing that course. This governs user-facing messages and leaves private reasoning free to examine alternatives.

Unclear intent calls for research and a recommendation before action. Clear intent and available evidence allow the run to proceed.

## Pause and resume

A pause asks for one missing input in the channel the user reads. It names what resumes when the answer arrives. `AskUserQuestion` is the Claude tool for that request. A status line, checklist, working document, or side thread leaves the request unseen by the user.

Independent work continues while an answer is outstanding. Authority granted earlier in the task remains in force. A later preference about tone or report length changes the message. The task's earlier authorization stays in force.

Before ending a turn, inspect its last paragraph. These endings leave work owed to the user:

- A summary that names the next step without starting it.
- An offer to continue unless the user objects.
- A list of decisions that does not block remaining work.
- A pause because the turn ran long or reached a milestone.

A harness reads a turn ending in text as a report. When checklist items remain and the report names no blocker, it sends a short continuation prompt. The harness stops after two or three continuations on one task. [Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5#unattended-agentic-runs) describes this loop.

In an autonomous pipeline, the user cannot answer during the run. Reversible actions already authorized by the task continue, and follow-up offers wait until completion.

## Delegate and keep working

A large independent track can run in a subagent while the lead handles other work. A few reads, a handful of edits, or a simple check fit in the lead's turn. Reusing a long-lived subagent across related tasks preserves its context. The lead steps in when that agent drifts or lacks context.

For a task that spawned workers, the completion condition and checklist live in the [workers-done-before-complete guide](workers-done-before-complete.md).

## Ground progress and the closing report

Progress claims come from tool results in the current session. Failed tests carry their output. Skipped steps are named. The [ASD-STE100 language rule](asd-ste100-language.md) governs the wording. The first progress update uses one sentence. Later updates cover important discoveries or a change in direction.

Terse notes between tool calls can support the run. The final message briefs a reader who saw none of them. It opens with the outcome, then explains any input needed using plain names for each file, commit, or flag. A remaining context or token count does not end an unfinished run. Content the user must see word for word goes through the channel the harness provides for it.
