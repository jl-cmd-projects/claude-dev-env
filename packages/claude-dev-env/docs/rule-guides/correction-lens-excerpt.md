# Correction lens excerpt

This file carries the Codex copy of [`rules/correction-lens.md`](../../rules/correction-lens.md). The Codex compatibility materializer projects the fenced block below into a managed `AGENTS.md`.

## Excerpt for repository-instruction sessions

Codex reads its repository `AGENTS.md`; this excerpt supplies the standalone
contract.

```
Correction handling for this run, from rules/correction-lens.md.

When the user corrects you, fix the instance in front of you. Then post the
correction as a GitHub issue labelled `correction` on the repository of the
corrected work: the repository of the session's checkout, read from its origin
remote. Put the correction, what was asked, what the agent did, what the user
wanted, where, the evidence, and whether it repeats in the body, with secrets
masked, and personal detail masked on a public repository. Name the issue in
your reply. Build no control and open no pull request for it in this run.

When the repository cannot take the issue, post it on the private correction
inbox and say why. With no inbox, print the brief in your reply.

Whoever picks up the issue lands the lesson at the highest layer that can hold
it:

1. Codebase. The mistake is impossible by how the code is written: a type, a
   signature, a data structure, an API shape.
2. Static analysis. A program reads the tree and decides: a lint rule, an
   enforcer check, a paired test, a CI gate.
3. Review tooling. A reviewer or a review bot reads the criterion: a code-rules
   row, a BUGBOT pointer, a Graphite rule.
4. Skill. An agent follows a procedure.
5. Style guide. Word choice and prose shape.

The same correction arriving twice means the layer was too low. Move it up one
layer and say so. A memory file records the decision and encodes nothing.
```
