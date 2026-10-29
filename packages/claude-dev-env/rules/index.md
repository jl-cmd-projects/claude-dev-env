# Rules
Each line names a rule and its trigger. When its trigger matches your task, open the guide and follow it in full.

- **Plain language** ([guide](../docs/rule-guides/asd-ste100-language.md)). Writing chat, narration, or repository prose.
- **No contrast framing** ([guide](../docs/rule-guides/no-contrast-framing.md)). Any sentence a person reads.
- **Research mode** ([guide](../docs/rule-guides/research-mode.md)). Any claim, recommendation, or advice.
- **Verify before asking** ([guide](../docs/rule-guides/verify-before-asking.md)). Before a clarifying question.
- **Verified work** ([guide](../docs/rule-guides/verified-work.md)). Any task.
- **Verify runtime state** ([guide](../docs/rule-guides/verify-runtime-state.md)). Before you say a component works, is healthy, or is not the cause.
- **Explore thoroughly** ([guide](../docs/rule-guides/explore-thoroughly.md)). Before you log, plan, delegate, or build an ask.
- **Features start with an eval** ([guide](../docs/rule-guides/features-start-with-an-eval.md)). New feature or behavior change.
- **Request scope** ([guide](../docs/rule-guides/request-scope.md)). Asked whether part of a block is still needed, or asked to change one.
- **Shell invocation** ([guide](../docs/rule-guides/shell-invocation.md)). Any Bash command or permission rule.
- **Destructive commands** ([guide](../docs/rule-guides/destructive-commands.md)). Removing files.
- **Filesystem search** ([guide](../docs/rule-guides/filesystem-search.md)). Finding files by name, path, size, or date.
- **Clean up temporary files** ([guide](../docs/rule-guides/cleanup-temp-files.md)). Creating scratch files or debug dumps.
- **Pull request lifecycle**. Before a commit, push, pull request action, or merge. Invoke the `pr-lifecycle` skill; a hook denies those commands until it loads.
- **Proof before a pull request** ([guide](../docs/rule-guides/proof-before-pull-request.md)). Before you open a pull request.
- **Session title** ([guide](../docs/rule-guides/session-title.md)). The session has a tool whose name ends in `__set_session_title`.
- **Durable facts only** ([guide](../docs/rule-guides/memory-stores-durable-facts.md)). Writing auto-memory or a `MEMORY.md` entry.
