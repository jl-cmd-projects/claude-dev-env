# Review criteria

Apply these to the diff. Report a finding only after checking it against the code.

- Review supported behavior and the changed repository contract. Current instructions override a stale copy. A contract change is not a defect because an older rule differs.
- Name a reachable caller, a supported input, and an observable failure for each defect.
- Check command flags, the environment, the pipeline, and the executable path before calling a command read-only.
- Security and atomicity findings need deployment and trust-boundary evidence.
- Coverage advice is separate from a demonstrated defect.
- A changed context file that passes the context budget and still carries detail a pointer should hold is a finding.
- Bind a delayed event, a cancellation, and review evidence to the full candidate head.
- A finished review can contain findings. A resolved thread, a timeout, or a quota notice does not prove a repair.
- Only a verified pass on the current head supports admission.

## Finding block

An empty list is a valid review. End with a json block. Each finding has `file`, `line`, `priority`, `summary`, and `failure_scenario`. Priority 0 blocks the merge. Priority 1 is fixed before the merge. Priority 2 can follow the merge. Priority 3 is a style nit.

## Loop

Fix every finding that holds, including a file the diff did not touch. Before a pull request opens, one pass runs and its fixes need no second pass. On the pull request, the review stops after three full passes with fixes, and a later pass files what it still finds in one issue. [The pr-lifecycle review loop](../../pr-lifecycle/reference/review-loop-before-merge.md) holds both rules.
