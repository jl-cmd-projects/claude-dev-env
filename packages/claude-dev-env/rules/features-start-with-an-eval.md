# Features start with an eval

**When:** A user asks for a new feature or a change in behavior.

Your first action is the Skill tool with skill `claude-api` and args `build-eval`. Build the feature against that eval. When the work touches an existing feature with no eval, start a separate session to build that eval in parallel. An Agent-tool subagent does not count. You own its result.

**Enforcement:** `hooks/blocking/pr_lifecycle_skill_gate.py` denies a `feat` pull request with no "Eval" section or no build-eval call.

**Full text:** [guide](../docs/rule-guides/features-start-with-an-eval.md).
