# Context budget

Use this page for "is this context file thin enough?" and "check the context budget".

An entry file is a short map. Detail lives in reference files the agent opens on demand. The repository's `.claude/context-budget.json` names each kind of context file, its line limit, and whether the section rule applies. Its baseline lists the files and hooks that were over budget when the list was built. A listed item may only shrink.

## Check one file

Run from inside the repository whose policy applies:

```text
python packages/claude-dev-env/scripts/context_budget_check.py <path> [<path> ...]
```

Each file's committed `HEAD` version is its prior state, so the grown and ratchet checks work outside a pull request. The command prints `context-budget: OK (<n> checked)` and exits 0 when every file is within budget. Otherwise it prints one finding per line and exits 1.

## Check the hooks

```text
python packages/claude-dev-env/scripts/context_budget_check.py --hooks
```

It runs each hook in the policy's `hooks` list and prints the characters each one injects, its limit, and its baseline.

## Fix a finding

| Finding | Fix |
| --- | --- |
| `section "<heading>" has <n> detail lines and no pointer` | Move the section body to `reference/<kebab-heading>.md` and leave a one-line link to it. |
| `file has <n> lines (<kind> limit <limit>)` | Move detail sections to reference files and leave one-line links. |
| `grew from <n> to <m> lines` | Move detail out until the file is back to its recorded count or fewer. |
| `file is below its over-budget entry` | Set the entry to the numbers the message gives, or remove it. |
| `the over-budget list may only shrink` | Restore the prior policy value and shrink the context instead. |
| `hook "<name>" injects <n> characters` | Move the hook's text to a skill or reference file and inject a pointer. |

## Rebuild the over-budget list

A person never edits the baseline by hand. After a change shrinks listed files, rebuild it:

```text
python packages/claude-dev-env/scripts/context_budget_check.py --write-baseline
```

## Where it runs

- The `context-budget` and `context-budget-policy` rules in `cde_lint` run in CI on every pull request.
- The write hook `hooks/blocking/context_budget_blocker.py` denies a Write, Edit, MultiEdit, or apply_patch that grows a context file, in any repository the session edits.
- `hooks/test_context_budget_hooks.py` holds each listed hook to its budget.
