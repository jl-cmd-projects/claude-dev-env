---
name: e-teamwork
description: >-
  Hand off a request to an autonomous multi-agent team that runs an optional
  upfront interview, splits work across specialist subagents, and relays
  updates back to the user. Triggers: /e-teamwork.
---

# e-teamwork

Hand the user's request over to an autonomous **team lead** subagent as it is—do
not attempt the task yourself in the main conversation.

## Intake and Handoff Rules

1. **Empty-request check:** If the request after `/e-teamwork` and any leading
   bracket parameters (such as `[skip-interview]`) is empty, ask the user what
   they want the team to do before spawning anything.
2. **Preserve parameters verbatim:** Strip `/e-teamwork`, keep any leading
   bracket parameters such as `[skip-interview]` at the start of the task prompt
   exactly as typed, and add none the user did not type.
3. **Append referenced context:** The spawned team cannot see this conversation
   history. When the request refers to earlier turns here, append the relevant
   parts quoted inside the handoff prompt.
4. **Spawn the team lead:** Launch a dedicated team-lead subagent using your
   host's subagent-spawning tool with the prepared prompt and the workflow in
   [the team workflow guide](reference/team-workflow.md).
5. **Relay loop:** When the team lead (or its interviewer step) sends back
   updates, clarifying questions, or drafts for the user, follow the
   instructions in that message and relay them cleanly. When the user asks how
   the work is going, query the active team-lead subagent rather than inspecting
   work inline.

## Reference

- [Team workflow](reference/team-workflow.md) — interviewer pass, `[skip-interview]` handling, specialist delegation, context forwarding, and relay loop.
