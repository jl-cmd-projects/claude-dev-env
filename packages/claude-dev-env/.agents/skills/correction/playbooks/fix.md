# Fix

Use this playbook when this session lands the fix for the correction itself. One correction gets one control and one pull request.

1. Write the brief from [`../SKILL.md`](../SKILL.md) first. It is the record every later step reads.
2. When pstack is loaded, invoke `/pstack:poteto-mode`, then `/correct`. Point `/correct` at the brief's mistake alone, and skip its sweep of the whole repository.
3. Read the correction instructions of the repository the mistake happened in. Open each `AGENTS.md` or `CLAUDE.md` index line that names corrections, and any intake note it points to. Where they name the target repository, the proof, or the run route, they win over this playbook.
4. Search for an existing control: a rule, hook, lint, test, or skill that already names this mistake. A control that exists and still let the mistake through makes this a repeat.
5. Choose the layer with [`correction-lens.md`](../../../../docs/rule-guides/correction-lens.md). When `Repeat` is `yes`, or step 4 found a control, go one layer above the one that failed.
6. Land the control in the repository whose code, CI, or agents it guards, per the guide's "Where the control lands" section. When that repository is not in this session, add it. When it cannot be added, print the brief, name the missing repository, and stop.
7. Prove the control. Show it fail on the mistake from the brief's `Evidence` line, then pass with the change, per [`falsify-before-green.md`](../../../../rules/falsify-before-green.md) and [`proof-before-pull-request.md`](../../../../docs/rule-guides/proof-before-pull-request.md). Without that proof, open no pull request.
8. Open the pull request through `pr-lifecycle`. Put the brief, the layer, and both proof results in the body.

**Reply:** the layer chosen, why each higher layer cannot hold the lesson, and the pull request link.
