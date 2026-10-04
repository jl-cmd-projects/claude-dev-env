# Workflow substitution slots

Full text behind [`rules/workflow-substitution-slots.md`](../../rules/workflow-substitution-slots.md).

## Values in agent-prompt templates

An agent fills angle-bracket slots such as `<plate.svg>`, `<object.svg>`, and `<glow_hex>` for each call. The same convention applies to an iteration index in a path or output key. `cand_<i>` names a changing path segment. `cand_i` names one literal directory, so repeated iterations can overwrite the same output and collapse an N-iteration gate into one run.

For a looped path or key, use `cand_<i>`. Step text can instead say `replace <i> with the iteration index 0, 1, 2`. Each call then gets its own value.

## Enforcement

The staged policy lint runs `workflow-substitution` on `.workflow.js` files. It reports a bare `<word>_<i|j|k>` token used as a path segment in looped content. CI runs the lint against the merge base. A write-time hook does not report this case, so the token remains on disk until lint runs.
