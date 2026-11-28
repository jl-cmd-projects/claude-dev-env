---
name: handoff
description: "Write a handoff for moving work to a new session in a different environment. Use when the user types /handoff or says they are moving the work to another session."
---

# Handoff

I'm moving this work to a new session in a totally different environment. If you have workers, background jobs or watchers running, pause that work now and stop them at a safe point. Commit and push everything to branches on the repo, so a session outside your environment can reach all of it. Confirm that no worktree has uncommitted or unpushed work.

Then write one handoff, in the first person, as if I wrote it. It must be complete on its own: everything the next session needs is either in the handoff or in a pushed branch, with no local files, scratch paths or session-only state.

## Structure

1. **The goal.** The one bar the work must reach, and the constraints that hold whatever route is taken.
2. **Open route.** The next session may reach the goal any way that works. Use the world as your oyster. It is free to rebuild, replace or question anything I built. What I built is a starting point.
3. **Where it stands.** Current measured results, with links to the runs.
4. **What I built and tried.** Every pull request and branch, with links, bases, heads and status, and the specific steps tried and what each measured.
5. **Done when.** Concrete, checkable finish lines.

## Rules

- State only what is true now and needed to continue. Read the live state of each pull request, branch and run before you write it.
- State only work that was done.
- Leave out how-to-work advice, tooling tips, and blockers that were specific to your environment.
- Leave out every out: no optional steps, "if possible", "or report why", fallbacks, or any wording that lets an agent stop short of the goal.
- Be concise. A 12 year old should be able to read the handoff and understand it. Use no jargon.
