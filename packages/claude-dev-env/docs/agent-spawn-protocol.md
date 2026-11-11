# Agent Spawn Protocol

Full protocol for briefing a subagent. It applies before any Agent or Task tool invocation — Explore, implementation, research, or team subagents.

## Step 1: Context sufficiency check

Before writing any agent prompt, confirm you can answer all of these:

- What specific files, directories, or areas of the codebase are involved?
- What constraints apply — patterns to follow, things to leave untouched, boundaries?
- What does success look like — expected output, acceptance criteria?
- Is the task unambiguous enough to delegate?

When any answer is "I don't know", investigate first (read files, search code) or ask the user. Do not spawn with incomplete context.

## Step 2: Write the prompt

Write the brief yourself. Include:

- The task description and goal
- Target files and directories found in Step 1
- Constraints and boundaries
- Expected output format
- Acceptance criteria

Use the brief as the agent's `prompt` parameter.

## Step 3: Spawn the agent

Pass the structured prompt from Step 2 to the Agent or Task tool. Set the model and the effort from [Subagent model and effort](rule-guides/subagent-model-effort.md). The work decides the model, as [Which model for which job](model-choice/which-model.md) says, and a side task such as search or log reading goes to a cheaper model, as [Subagents and fan-out](model-choice/subagents-and-fan-out.md) says.

## Why

An agent that receives a vague prompt wastes tokens exploring in circles, produces code that misses constraints, and needs a second pass. A small investment in prompt quality saves a long agent failure. This holds for Explore agents, which waste context on unfocused searches, and for execution agents, which write wrong code.

## Relationship to other rules

- Acting when intent is ambiguous goes to investigation or a user question first, never straight to a subagent; this protocol extends that guard to the spawn decision itself.
- Project-specific rules or `~/.claude/CLAUDE.md` may decide whether to use subagents at all; this protocol governs how to craft the prompt once you delegate.
