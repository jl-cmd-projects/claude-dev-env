# Team Workflow

How the team lead executes a `/e-teamwork` handoff using standard subagent and
workspace tools, without any host-specific built-in team runtime.

## 1. Upfront Interview (Default)

Unless the prompt begins with `[skip-interview]`, run a short interviewer pass
before launching specialist workers:

- Identify ambiguities that materially change scope, architecture, target
  files, or acceptance criteria.
- Send one focused set of clarifying questions back to the parent agent to
  relay to the user.
- Wait for the parent to return the user's answers before starting execution.
- When `[skip-interview]` appears at the start of the prompt, skip this pass
  and move directly to planning.

## 2. Specialist Delegation

Once requirements are clear:

1. **Decompose:** Split the work into bounded specialist roles (researcher,
   implementer, verifier) with disjoint file ownership so concurrent authors
   never collide.
2. **Brief from scratch:** Every specialist subagent starts with an empty
   history. Include the user's goal, quoted prior decisions, owned file paths,
   constraints, and concrete verification criteria in each brief.
3. **Verify before reporting:** Assign a fresh verifier subagent to run tests
   or checks against completed changes before reporting the task done.

## 3. Parent Relay, Status, and Fallbacks

- **Updates, questions, and drafts:** Send explicit instructions to the parent
  agent describing what to show the user and what reply is needed back.
- **Status inquiries:** When the user asks how work is progressing, the parent
  queries the active team-lead subagent and reports current specialist states,
  completed milestones, and open blockers.
- **No subagent support:** When a host environment provides no subagent tool,
  report that limitation cleanly to the user before attempting workarounds.
