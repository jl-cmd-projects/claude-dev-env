Back to the [rules index](../../rules/index.md).

# DeepStack wording

## In brief

A deepened task uses the three DeepStack labels and puts `CDE_DEEPEN:v1` on line 1. The gate in `hooks/session/deepen_first_prompt.py` is the check. This guide cites that gate.

**When this applies:** Writing a deepened task, a worker prompt, or a sentence that names the three DeepStack lines.

## Labels

- `SCOPE (role):` names the standing job in one sentence.
- `EXAMPLES (illustration only):` lists each example, or `none`.
- `ZOOM-IN BLOCKER:` names why the standing job cannot proceed, or `none`.

Say "the user" in public text.

## Where it is enforced

| Surface | What runs |
|---|---|
| A first-task rewrite | `hooks/session/deepen_first_prompt.py` |
