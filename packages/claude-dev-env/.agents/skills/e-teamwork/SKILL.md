---
name: e-teamwork
description: >-
  Hand off a request to an autonomous multi-agent team that runs an optional
  upfront interview, splits work across specialist subagents, and relays
  updates back to the user. Triggers: /e-teamwork.
---

# e-teamwork

Hand the user's request over to an autonomous team-lead subagent as it is.
Leave task execution to the spawned team while the main conversation handles
intake and user communication.

## Intake and Handoff Rules

1. **Empty-request check:** When `/e-teamwork` arrives with no task text beyond
   optional bracket parameters such as `[skip-interview]`, ask the user what
   they want the team to do before spawning anything.
2. **Preserve parameters verbatim:** Strip `/e-teamwork`, keep any leading
   bracket parameters such as `[skip-interview]` at the start of the task
   prompt exactly as typed, and add none the user did not type.
3. **Append referenced context:** The spawned team starts with an isolated
   history. Append quoted excerpts of any earlier conversation context the
   request references.
4. **Spawn the team lead:** Launch a team-lead subagent using your host's
   subagent-spawning tool with the prepared prompt and the procedure in
   [the team workflow guide](reference/team-workflow.md). When the host lacks
   subagent spawning, inform the user clearly that multi-agent delegation
   requires subagent support in the session.
5. **Relay loop:** Forward clarifying questions, drafts, and progress updates
   from the team lead to the user, and route user answers and status inquiries
   back to that active team-lead subagent.

## Reference

- [Team workflow](reference/team-workflow.md)
