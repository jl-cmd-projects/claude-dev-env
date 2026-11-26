# Team Workflow

How the team lead executes a `/e-teamwork` handoff using standard subagent and
workspace tools, without depending on any host-specific built-in team runtime.

## 1. Upfront Interview (Default)

Unless the prompt starts with `[skip-interview]`, begin with a short
**interviewer** pass before launching implementation workers:

- Identify ambiguities that materially change scope, architecture, target
  files, or acceptance criteria.
- Send one focused set of clarifying questions back to the parent agent so the
  parent can relay them to the user.
- Pause execution until the parent forwards the user's answers.
- When `[skip-interview]` is present at the start of the prompt, skip this
  interview and start planning immediately.

## 2. Specialist Delegation

Once requirements are clear:

1. **Decompose:** Split the work into bounded specialist roles (for example
   researcher, implementer, tester/verifier) with explicit ownership so two
   authors never edit the same file concurrently.
2. **Brief from scratch:** Every specialist subagent starts with an empty
   history. Include the user's goal, quoted prior decisions, owned file paths,
   constraints, and concrete verification criteria in each brief.
3. **Verify before reporting:** Have a fresh verifier subagent run tests or
   checks against the completed changes before declaring the task done.

## 3. Parent Relay and Status Routing

- **Updates, questions, and drafts:** Message the parent agent with explicit
  instructions on what to present to the user and what response is needed back.
- **Status inquiries:** When the user asks how the work is going, the parent
  checks the active team-lead subagent and summarizes current specialist states,
  completed milestones, and open blockers.
- **Completion:** Present the verified outcome, modified files, and test
  results back to the parent once all specialist tasks pass verification.
