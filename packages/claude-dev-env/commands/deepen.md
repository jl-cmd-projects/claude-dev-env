---
description: Deepen a task into the omitted expert job before work starts
argument-hint: [task to deepen]
---

Deepen this task before any work starts: `$ARGUMENTS`

When `$ARGUMENTS` is empty, ask the user to paste the task and stop.

When `$ARGUMENTS` holds a task, answer four things the prompt left out:

1. What a top person in that field would do that this prompt omitted.
2. The raw source to start from.
3. The methods and tools they would use.
4. What besides the agent or Jon would show the result is right.

Rewrite the task so it asks for exactly that job. Put `CDE_DEEPEN:v1` at the top of the rewrite. Then do only that job.

Skip this command when the prompt already carries `CDE_DEEPEN:v1`.
