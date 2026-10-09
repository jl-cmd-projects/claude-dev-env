# Verify runtime state

**When:** Before saying a component works, is healthy, or is not the cause of a failure.

Gather a live signal this session: process list, port probe, log, status code, or fresh reproduction. Read the user's terminal and named error log while a reported failure is still visible. Check the effect the work should produce, including each job result, loaded config, or deployed artifact; a success status alone does not establish the effect. When testing code, identify the loaded module path.

**Enforcement:** none.

**Full text:** [guide](../docs/rule-guides/verify-runtime-state.md). Read it when choosing the probe for a claim.
