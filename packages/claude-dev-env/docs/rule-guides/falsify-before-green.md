# Falsify before green

Full text behind [`rules/falsify-before-green.md`](../../rules/falsify-before-green.md).

## The four shapes this stops

### 1. A probe whose trigger condition never fires

The probe reports zero while its counter stays at the start value. The trip input exposes whether it observes an event.

**Break to apply:** feed it one input that must trip it. A probe still at zero on that input measures nothing.

### 2. A sweep that reads a subset of the files it claims to cover

The sweep may compare against the wrong base or walk a slice of the tree while claiming the full set.

**Break to apply:** plant one violation in a file the sweep's coverage claim names. A sweep that misses the plant walks a smaller file set than the one it reports.

### 3. A mutation that survives

The test may miss the mutated code because a mock stands in for the call, a guard returns early, or the test drives a neighboring branch.

**Break to apply:** hold the mutation in place and run the test. A green test names a line nothing covers.

### 4. An assertion that counts an artifact the harness seeded

The harness writes the row, file, or event the assertion counts. Stubbing the production writer exposes that source.

**Break to apply:** stub the production writer to a no-op. A green assertion counts the seed.

## What a shown-red record holds

| Part | What it names |
|---|---|
| The break | The mutation, stub, or trip input, named by file and line or by the exact input text |
| The red | The failing output the check printed under that break |
| The control | The case that passes beside the red, run on the same command |

The red and control distinguish a selective check from one that always fails or always passes.

## Enforcement

A reviewer reads the shown-red record beside each new check a pull request adds. A regex cannot tell which code a green check reached at run time.
