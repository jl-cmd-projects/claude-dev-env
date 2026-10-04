# Testing standards

Full text behind [`rules/testing.md`](../../rules/testing.md).

> **Reference:** [`TEST_QUALITY.md`](../TEST_QUALITY.md) for test review.

## Complete mocks for testability

If a component renders field X, a mock with a valid X value lets the test reach rendering behavior. An omitted field can make a failing render ambiguous.

## Tests exercise production behavior

A stand-in can satisfy an assertion while the production path stays untested. The behavior under review is the result of the production call.

## Test order

The TDD skill (`pstack:tdd`) carries the red, green, refactor procedure. No hook or lint checks the order. Review reads the reproducing test on the diff.

## Fix proof job

The `Fix test proof` job in `.github/workflows/pr-check.yml` runs `_shared/pr-loop/scripts/fix_pr_test_proof.py` on pull requests whose title starts with `fix`. Node proof tests end in `.test.mjs`, `.test.js`, or `.test.cjs`, and the job runs them with `node --test`. A docs-only or CI-only fix passes. A fix proven by a PowerShell test also needs Python or Node proof.
