# Features start with an eval

**When:** A user asks for a new feature or a change in behavior.

Your first action on the ask is the Skill tool with skill `claude-api` and args `build-eval`. Then search for existing work, and build the feature against the eval. When the work touches an existing feature that has no eval, start a separate session that builds that eval with the same command, in parallel with your work. An Agent-tool subagent is not a separate session. You own that session's result.

**Enforcement:** `hooks/blocking/pull_request_proof.py` denies a `feat` pull request with no "Eval" section naming a command, and one from a session that never invoked `/claude-api build-eval`.

**Full text:** [`docs/rule-guides/features-start-with-an-eval.md`](../docs/rule-guides/features-start-with-an-eval.md). Read it for what counts as a feature and an eval, and how to start the separate session.
