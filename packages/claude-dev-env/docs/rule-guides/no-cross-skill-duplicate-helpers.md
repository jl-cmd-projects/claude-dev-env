# Cross-skill duplicate helpers

Full text behind [`rules/no-cross-skill-duplicate-helpers.md`](../../rules/no-cross-skill-duplicate-helpers.md).

## The two duplication cases differ

CODE_RULES "Reuse before create" / DRY gives one helper one home within a skill. Two `.py` modules in the same skill's `scripts/` directory with the same top-level function body fail the `code_rules_duplicate_body` check. The staged policy lint runs it through `code_rules_enforcer.py`.

Each skill folder installs on its own. A shared module that lives in one skill would break the other skill after removal or reinstall. A small launch helper, such as one that reads the browser registry entry and starts `chrome.exe`, can live in each skill.

## Dependency choices

A large helper may hold business logic or drift in ways that change behavior. The user chooses between two arrangements:

- Copy the helper into each skill and accept the drift risk.
- Declare a shared dependency in both skills. A published package in both `requirements` files or a `_shared` module installed into each skill can survive independent installation.

## What the advisory tells you

The `advise_cross_skill_duplicate_helper` check in `code_rules_duplicate_body` prints to stderr when a changed top-level function matches a helper in another skill's `scripts/` directory. It leaves the lint passing. The message names the source skill and function for review. The advisory covers copies across skill folders; the blocking check covers copies within one skill.

## Why the checks have different scopes

The cross-skill advisory preserves the small-copy option that keeps skills independently installable. Its source-skill name gives the writer enough context to judge the copy. The blocking check handles duplication inside one skill.
