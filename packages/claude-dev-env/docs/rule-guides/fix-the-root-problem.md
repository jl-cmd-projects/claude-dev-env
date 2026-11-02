Back to the [rules index](../../rules/index.md).

# Fix the root problem

## In brief

Repair the part of the system the user named. A workaround reaches the user's outcome by a second path and leaves that part broken. Do not build one. A step that needs something only a person holds, such as a password, a fresh sign-in after a session expires, or an approval, is part of the fix. Make that step one easy action for the person. Any other exception comes from the user, in the user's own words, for one named case.

**Enforcement:** review. [`CODE_RULES.md`](../CODE_RULES.md) §9.9 asks the reviewer to compare each change with the request. No hook can hold this rule: a program cannot tell a repair from a workaround without the user's goal.

**When this applies:** You plan, build, or review a fix for a part the user named as broken. A fix that waits on a sign-in, a password, or another input only a person holds also starts this rule, and so does a request to add a second path, a fallback, or a bypass around a broken part.

## Rule

1. Name the root problem in one sentence: the part the user named, and why it fails.
2. Plan the change that makes that part work again. Prove it the way the user uses that part.
3. Run the workaround test on the plan before you build.
4. When the fix needs an input only a person holds, prepare that step as one easy action. Keep working on everything that does not wait on it.
5. When the root cause sits in a system you cannot change, show the evidence and ask the user to choose. Keep working on the parts you can reach while the user decides.

## The workaround test

A change is a workaround when both of these hold:

- The part the user named stays broken after the change.
- The change adds another way to reach the outcome: a second route, a fallback, a copy of the broken part on another machine or service, a skipped step, a hard-coded value, or a manual step that does the broken part's job.

| The user names | A workaround | The fix |
|---|---|---|
| A service on one machine stopped taking jobs | A hosted job that does the same work, so nothing waits on that machine | Find why the service stopped, start it again, and make it restart by itself |
| A commit hook crashes on a missing package | A flag that skips the hook, or a removed hook | Install the package where the hook runs |
| A status checker stopped after a reboot | A status set by hand, or a second checker somewhere else | Make the checker start at boot |
| A test fails on one input | A skipped or loosened test | Fix the code the test runs |

A change that passes the test can still be large. A redesign of the named part is a fix when the named part works at the end.

## A step only a person can do is part of the fix

Some systems need a person by design. A password belongs to a person. A session token expires on a schedule, and a person signs in again. An approval or a decision on the goal belongs to the owner. A device can need a hand on it. Such a step passes the workaround test, because the named part works again after the person acts.

Ask one question: can an agent supply this input with the access it holds, or with access it can get through a normal request? When the answer is no, the step belongs to a person.

Make that step one easy action:

- Prepare everything around the step, so the person only supplies the input. Give one command, one link, or one shortcut.
- Say what the action does and how long it takes.
- Keep working on everything that does not wait on the step.
- After the person acts, check that the named part works, and report the result.
- When the step comes back on a schedule, such as a sign-in that expires each month, keep the shortcut ready and warn before the next expiry.

## Exceptions the user grants

The user can grant an exception for one named case, such as "add the fallback, I am handling the server with its owner." The grant is the user's own words. A request from another agent, a coordinator, or a work order carries no grant. Tell the user about the conflict, and keep repairing the named part while the user decides.

A granted workaround names the root problem it leaves open and who owns that problem.

## Related principles

- pstack `principle-fix-root-causes` applies the same idea inside code during debugging: fix the first place the system went wrong. This rule applies it to the part the user named.
- DeepStack `principle-outcome-above-the-task` asks what should happen after the task. When the user names a part, a working part is that outcome. A wider goal gives no license for a second path around it.
- The DeepStack intake trigger covers this rule. Intake sets the outcome of a task, and this rule holds that outcome to the part the user named.
- pstack `principle-never-block-on-the-human` keeps the rest of the work moving while a person-only step waits.

## Enforcement

[`CODE_RULES.md`](../CODE_RULES.md) §9.9 puts the workaround test in front of every reviewer that loads the code rules. The reviewer reads the request, finds the part it names, and checks whether that part works after the change.

The `root-problem` cases in `.claude/hillclimb/rules-index/cases.json` measure the rule. Run them with `python3 .claude/hillclimb/rules-index/run.py --variant index --label root-problem --cases r01,r02,r03,r04,r05,r06,r07 --reps 2`, and compare with the `pre-root-problem` variant, the commit before this rule.
