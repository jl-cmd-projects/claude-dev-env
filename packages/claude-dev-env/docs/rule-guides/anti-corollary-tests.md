# Anti-corollary tests

Full text behind [`rules/anti-corollary-tests.md`](../../rules/anti-corollary-tests.md).

## The three questions

### 1. Is this a corollary?

When the code reduces each input to a canonical form and then compares the forms, every pairwise combination of input spellings follows once the reduction is proven canonical. Walking the full N-by-N matrix restates that fact. It adds cases and runtime, and it buries the few cases that carry information.

### 2. Could this test pass if the mechanism were dead?

The degenerate value may be an empty string, `None`, `False`, a blanket refusal, or an empty collection. A test expecting that value passes even when the mechanism stops.

### 3. What single change to the code would make this test fail?

The named mutation identifies the behavior a case observes. A case that survives it provides no evidence about that behavior.

**The policy-surface case.** A test that asserts a policy's wording appears in its declaring file detects edits to that sentence. A suite of such tests counts repeated text. The declaring file can supply the policy while assertions inspect the surfaces it governs.

## What a mechanism with a degenerate failure mode needs

The audit record pairs a specific code mutation with the number of tests it fails. A reviewer or audit skill checks that record; no hook computes it.

## Worked shape (sanitized)

A write guard decides whether a write is about to hit a production database. It reduces each database URL to a canonical endpoint identity, then compares identities.

Two independent mutations show the two halves of a useful suite:

- Gut the reduction so it always returns the empty string. The guard fails **closed** and refuses everything. The *allow*-expecting cases die.
- Abandon the reduction and compare raw hostnames. The guard fails **open** and allows a production write. The *refuse*-expecting cases die.

The two breaks exercise opposite outcomes. A suite with both outcomes detects each break.

## Why this requires judgment

A structural hook cannot infer whether a case follows from canonicalization or passes against a dead implementation. Counting `parametrize` cases or assertions would also flag useful suites. The review and audit lanes judge changed tests using their intended behavior.

## Sibling rules

| Rule | Role |
|---|---|
| [`code-standards.md`](../../rules/code-standards.md) | Points at CODE_RULES section 8 on a failing test before production code |
| [`testing.md`](../../rules/testing.md) | Mocks and test infrastructure standards |
| [`paired-test-coverage.md`](../../rules/paired-test-coverage.md) | Every public function in an established suite gets a behavioral test |
| [`anti-corollary-tests.md`](../../rules/anti-corollary-tests.md) | Each test carries information |

## Enforcement

The AI review lane and audit skills inspect the test lines a pull request changes. No blocking hook evaluates the intent behind a corollary or dead-default case.
