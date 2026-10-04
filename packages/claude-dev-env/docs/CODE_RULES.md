# Code Rules Reference

Use this index for edits. [`.cursor/BUGBOT.md`](../../../.cursor/BUGBOT.md) points here. Open a linked guide when its trigger applies.

## COMMENT PRESERVATION

Do not add code comments. Preserve existing comments. Docstrings remain allowed.

When a change touches code that an existing comment describes or is attached to, remove that comment in the same change and carry its meaning through clear names and structure. Leave comments tied to untouched code unchanged. Keep comment cleanup inside the requested task.
Production and tests follow one rule. Changed directive, TODO, FIXME, HACK, XXX, and type-ignore comments are removed rather than added or justified.

A keep marker is the one comment that may be added and kept: a comment that opens with a prefix the repository lists under `comment_keep_markers` in `.claude/policy-lint.json`. Open [details](code-rules/comment-preservation.md) when editing comments.

## CORE PRINCIPLES

Use clear names. Keep shared constants in `config/`. Search before adding helpers. Put construction and formatting with the data owner. Encapsulation enables cleaner naming, so prefer `isMaxLevel(level)` to `level >= MAXIMUM_LEVEL`. Session policy lives in [`code-standards.md`](../rules/code-standards.md).

Open [details](code-rules/core-principles-and-config.md) when adding shared values or construction logic.

## ⚡ LINT-ENFORCED RULES

Staged lint runs `code_rules_enforcer.py`. Keep imports at the top, parameterize logging, guard path insertion, use specific exceptions, and follow checks for values, types, docstrings, names, and tests. Magic values exempt 0, 1, and -1. Type escape hatches are allowed in boundary files. Stub bodies are allowed in abstract and Protocol classes.

- UPPER_SNAKE constants belong in `config/`. Exemptions include `config/*`, `/migrations/`, and test paths or names matching `test_`, `_test.`, `.spec.`, `conftest`, or `/tests/`.
- Workflow registries: a path that contains any of these substrings, `/workflow/`, `_tab.py`, `/states.py`, or `/modules.py`, is exempt; each matches independently as a substring.

Open [details](code-rules/lint-enforced-rules.md) when lint fires.

## 3. REUSE CONSTANTS / 4. CONFIG LOCATIONS

Search `config/` for an exact or semantic match. Put timing in `config/timing.py`, ports and thresholds in `config/constants.py`, and selectors in `config/selectors.py`.

Open [details](code-rules/core-principles-and-config.md) when placing a new value.

## 5. NO ABBREVIATIONS

Use `context`; `ctx` is banned. Allow `i`/`j`/`k` in loops and `e` for exceptions. Patterns: `each_*` loops; `is_`/`has_`/`should_`/`can_`/`was_`/`did_` booleans; `all_*` collections; `X_by_Y` maps; `from_path=`, `to=`, `into=` parameters. Banned names: `result`, `data`, `output`, `response`, `value`, `item`, `temp`. Banned prefixes: `handle`, `process`, `manage`, `do`. Name components for their roles. Use `ItemBlocked` or `RunFatal` for failure scope; these suffixes bypass the banned-noun check.

### Public compatibility definitions

The banned-noun check applies to public function definitions, parameters, and body bindings. Use clear names in each.

Open [details](code-rules/naming-and-types.md) when naming code.

## 6. COMPLETE TYPE HINTS

Type every parameter and return. Avoid `Any` and `# type: ignore`; remove ignores and use a typed boundary or precise annotation. Annotate known pytest fixtures and remove unused fixture parameters.

Open [details](code-rules/naming-and-types.md) when a type or fixture check fires.

## 6.5 FILE LENGTH GUIDANCE

File length is advisory: emit a stderr advisory at 400 lines and a stronger stderr advisory at 1000 lines. Split on cohesion after a readability check.

Open [details](code-rules/design-and-structure.md) when a length advisory fires.

## 7. RIGHT-SIZED ENGINEERING

Use functions without state and concrete classes with state. Avoid ABCs, factories, and DI frameworks for one implementation. Add abstractions for multiple implementations. Add optional parameters when callers vary them; require or inline fixed values. Remove unused parameters.

Open [details](code-rules/design-and-structure.md) when adding a class or parameter.

## 7.5 SOLID PRINCIPLES

Apply SRP throughout. Apply OCP, LSP, ISP, and DIP when two concrete implementations share a contract. Keep cohesive classes together.

Open [details](code-rules/design-and-structure.md) when extracting a responsibility.

## 8. TDD PROCESS

For a bug fix or new behavior, run RED with a failing test, GREEN with the smallest change, then REFACTOR when useful. A prototype adds tests before its pull request goes ready. A bug fix ships with a reproducing test.

**Proof of check.** Each pull request body names a repeatable test, run, screenshot, or measurement. A reviewer flags a body with no proof.

Open [details](code-rules/tdd-and-proof.md) when adding behavior or proof.

## 9. SELF-CONTAINED COMPONENTS

Components own their state, modals, overlays, and toasts. Parents render `<Child />`.

Open [details](code-rules/design-and-structure.md) when splitting components.

## 9.5 NO THIN WRAPPER MODULES

Callers import the owning module directly. Keep re-exports in `__init__.py`; an imports-only non-`__init__.py` module is a thin wrapper.

Open [details](code-rules/design-and-structure.md) when moving modules.

## 9.6 NO BACKWARDS-COMPATIBILITY SHIMS

Remove renamed re-export aliases, old aliases, keep-alive wrappers, and tombstone markers. Update call sites in the same change when a symbol changes.

Open [details](code-rules/design-and-structure.md) when renaming symbols.

## 9.7 NO FALLBACK / BEST-EFFORT WRAPPERS

Never swallow a failure into a default unless the caller explicitly opted in at the boundary. Name the specific exception (`except KeyError:`) and propagate the rest. Collapsing every error class to `None` masks programming errors and makes debugging impossible.

Open [details](code-rules/design-and-structure.md) when handling batch failures.

## 9.8 REMOVE CODE YOU ORPHAN (Dead Code Elimination)

Remove orphaned variables, functions, parameters, branches, imports, and helpers. Check references and dynamic lookups first. Remove dead self-referential clusters. **When liveness is uncertain (public API, plugin hook, reflective dispatch), surface the ambiguity and never delete.**

Open [details](code-rules/design-and-structure.md) when removing consumers.

## 10. NO REDUNDANT DATA FETCHES

Use data already in hand; do not fetch it again.

Open [details](code-rules/design-and-structure.md) when reviewing fetches.

## 11. ENFORCEMENT SURFACES

Lint checks patterns; prompts carry judgment; rubrics cover cross-file concerns.

Open [details](code-rules/enforcement-surfaces.md) when routing a rule.

## 11.5 VALIDATION-PHASE PRECEDENCE

Phase selects checks; target classification narrows them; changed-line scope filters findings. Each axis narrows the previous one.

Open [details](code-rules/enforcement-surfaces.md) when routing a check.

## 11.6 LANE ASSIGNMENT IS BY SCOPE

Scope assigns the lane. A check that reads a file other than the target runs on the full gate. Every other check runs on both lanes.

Open [details](code-rules/enforcement-surfaces.md) when adding a check.
