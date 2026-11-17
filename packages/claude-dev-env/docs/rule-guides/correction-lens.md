Back to the [rule entry](../../rules/correction-lens.md).

# Correction lens

**Standing rule. This file is never archived and never removed.** The permanence
clause at the end of this document states what that binds.

**When this applies:** Every correction the user gives. A "no, do it this way", a
"stop writing that word", a repeated review comment, a fix the user makes by hand
after an agent hands work back. Each one is evidence that a control is missing.
The corrected agent records that evidence as an issue, and a later session builds
the control from it on purpose.

## In brief

Fix the instance in front of you. Post the correction as an issue labelled `correction` on the repository of the corrected work, and name the issue in your reply. Build no control and open no pull request for it in this run, unless the user typed `/correction fix`. Whoever picks up the issue lands the control at the highest capable layer.

## What the corrected agent does

1. Fix the instance in front of you: the reply, file, or command the user corrected.
2. Write the brief the [`correction` skill](../../.agents/skills/correction/SKILL.md) defines. It carries the correction, what was asked, what the agent did, what the user wanted, where, the evidence, whether it repeats, and a suggested layer when one is clear.
3. Post it with the skill's `correction_filing.py`. The script picks the repository, adds the `correction` label, masks secrets and, on a public repository, personal detail, and marks a repeat on the earlier issue.
4. Name the issue in your reply with the line the script printed. When it posted to the fallback inbox, or posted nothing, say why.

The repository is the one whose work the user corrected. A correction to work on a themes automation repository goes on that repository, and a correction to the agent tooling goes on the tooling repository. The script reads it from the `origin` remote of the session's checkout, so a worktree resolves to its repository. When the session has no repository, or that repository has no GitHub access or has issues turned off, the script posts on the private fallback inbox and says why. With no inbox it posts nothing, and the agent prints the brief in its reply. [`references/filing.md`](../../.agents/skills/correction/references/filing.md) carries the details.

## Layers, for whoever picks up the issue

A correction runs through five layers, in this order, and the lesson lands at the
highest layer that can hold it. The issue may name a suggested layer. The session
that picks up the issue decides it.

| Priority | Layer | What holds the lesson | The lesson lands as |
|---|---|---|---|
| 1 | Codebase | The mistake is impossible by how the code is written | A type, a signature, a data structure, an API shape, a deleted branch |
| 2 | Static analysis | A program reads the tree and decides | A lint rule, an enforcer check, a paired test, a CI gate |
| 3 | Review tooling | A reviewer or a review bot reads the criterion | A `CODE_RULES.md` row, a `.cursor/BUGBOT.md` pointer, a Graphite or BugBot rule |
| 4 | Skill | An agent follows a procedure | A skill under the agents home |
| 5 | Style guide | Word choice and prose shape | A row in a `rules/*.md` file or a style document |

Layer 1 is the goal every time. A lesson encoded there needs no reader, no run,
and no agent to remember it. The wrong call has nowhere to live.

## Choosing the layer

Three sentences close every correction issue:

1. The layer chosen.
2. Why each higher layer cannot hold this lesson.
3. The change opened at the chosen layer, by a pull request that closes the issue.

A layer holds a lesson when its own test passes:

- **Layer 1 holds it** when a type, a signature, or a data structure can make the
  wrong call fail to compile, fail to construct, or fail to exist.
- **Layer 2 holds it** when a program reading the tree can separate right from
  wrong with no judgment call.
- **Layer 3 holds it** when a reader needs the criterion in front of them and a
  program cannot decide it.
- **Layer 4 holds it** when the lesson is a procedure with steps an agent runs.
- **Layer 5 holds it** when the lesson is word choice or the shape of prose.

Effort rules out no layer. A layer is ruled out when it lacks the capability to
hold the lesson, and the sentence that rules it out says which capability is
missing. "A lint for this would take a day" leaves layer 2 in play.

Two layers often hold one correction. Take both: the shape at layer 1 and the
check at layer 2 cost one run together and each covers what the other misses.

## A repeated correction moves up a layer

The same correction arriving a second time is the measurement. The layer chosen
the first time was too low. The filing script marks the repeat: a comment on the
open issue, or a new issue that links the closed one. Whoever picks it up moves
the lesson one layer up and says so.

A review comment that repeats across pull requests reads the same way. Each
repetition names the layer below the reviewer as the one that needs the control.
Count the repetitions.

## Where the control lands

A control lands in the repository whose code, CI, or pipeline it guards. A
control for one repository's workflows, review bots, pipelines, or agents lands
in that repository. This package takes only repo-agnostic controls, the
environment and development pieces any repository could use, so every session
that loads this environment carries them. A control written into one project's
instructions reaches that project alone, and a control written into a chat reply
reaches that conversation alone.

Memory holds the decision. The control holds the behavior. A correction that
produced a memory file and no issue is recorded where no fixer looks, so the rule
still binds. Post the issue.

## Trust grows as the controls catch the common mistakes

Add agents after the controls catch what agents get wrong, and start from a
workflow small enough to watch. Each repeated correction becomes a stronger
control, and the number of agents rises behind it.
[`docs/high-trust-agent-delivery.md`](../high-trust-agent-delivery.md)
carries the model this comes from, including the layered-controls picture and
the inner and outer delivery loops.

## Permanence

This file stays in `rules/`. A prune pass, an archive sweep, a consolidation, or
a rewrite that would move it into `rules-archived/` stops at this line. The
"Never archived" section of
[`packages/claude-dev-env/rules-archived/ARCHIVE-MANIFEST.md`](../../rules-archived/ARCHIVE-MANIFEST.md)
names it, and
[`archiving-agent-config.md`](../../rules/archiving-agent-config.md) names the same
exemption from the archiving procedure's side.

An edit that sharpens this rule is welcome. The file stays.

## Codex copy

Codex reads its repository `AGENTS.md`. The standalone excerpt it receives lives in [`docs/rule-guides/correction-lens-excerpt.md`](correction-lens-excerpt.md).

## Sibling rules

| Rule | Role |
|---|---|
| [`flag-non-breaking-findings.md`](../../rules/flag-non-breaking-findings.md) | A gate blocks on a breaking finding and records a smell |
| [`code-standards.md`](../../rules/code-standards.md) | The layer map of contract, pointer, enforcer, lint, session rules |
| [`archiving-agent-config.md`](../../rules/archiving-agent-config.md) | How a rule leaves service, and which files are exempt |
| [`falsify-before-green.md`](../../rules/falsify-before-green.md) | A new layer-2 check counts once it has run red on a named break |
