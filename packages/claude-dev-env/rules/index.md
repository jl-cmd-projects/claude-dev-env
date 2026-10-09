# Rules
Each line gives a rule in brief. When its trigger matches your task, open the guide and follow it in full. Correction lens and question presentation load as their own files.

**Writing**
- **Plain language** ([guide](../docs/rule-guides/asd-ste100-language.md)). Writing chat, narration, or repository prose. Short complete sentences on one topic, active voice, one action per step, each fact said once.
- **No contrast framing** ([guide](../docs/rule-guides/no-contrast-framing.md)). Any sentence a person reads. State the chosen point and leave out the discarded reading. Remove the six forms: `trailing-comma-not`, `corrective-it-is-not`, `substitution-rather-than`, `additive-not-just`, `comparative-ranking`, `substitution-as-opposed-to`.

**Evidence**
- **Research mode** ([guide](../docs/rule-guides/research-mode.md)). Any claim, recommendation, or advice. Cite a source for each claim, and run the tool that settles a fact before you state it.
- **Verify before asking** ([guide](../docs/rule-guides/verify-before-asking.md)). Before a clarifying question. Look in files, config, environment, and tools first; ask only for a judgment or a preference.
- **Verify runtime state** ([guide](../docs/rule-guides/verify-runtime-state.md)). Before you say a component works, is healthy, or is not the cause. Get a live signal this session.

**Before building**
- **Explore thoroughly** ([guide](../docs/rule-guides/explore-thoroughly.md)). Before you log, plan, delegate, or build an ask. Search for existing work; when something exists, stop and report it in four points with the `search-before-acting` skill.
- **Features start with an eval** ([guide](../docs/rule-guides/features-start-with-an-eval.md)). A new feature or a change in behavior. Your first action is the Skill tool with skill `claude-api` and args `build-eval`.
- **Request scope** ([guide](../docs/rule-guides/request-scope.md)). Asked whether part of a block is still needed, or asked to change one. Propose removing every line a shipped gate already enforces.

**Shell and files**
- **Shell invocation** ([guide](../docs/rule-guides/shell-invocation.md)). Any Bash command or permission rule. Use `pwsh` on Windows; keep `$(...)`, backticks, and process substitution out of commands.
- **Destructive commands** ([guide](../docs/rule-guides/destructive-commands.md)). Removing files. Keep `rm` literals out of commands, use absolute targets, use `git rm` for tracked files, and copy the guide's no-rm line into subagent prompts.
- **Filesystem search** ([guide](../docs/rule-guides/filesystem-search.md)). Finding files by name, path, size, or date. Scope the search to a project, worktree, or filter, never a root.
- **Clean up temporary files** ([guide](../docs/rule-guides/cleanup-temp-files.md)). Creating scratch files or debug dumps. Track them and remove them when the task ends.

**Shipping**
- **Pull request lifecycle**. Before a commit, push, pull request action, or merge. Invoke the `pr-lifecycle` skill; a hook denies those commands until it loads.
- **Proof before a pull request** ([guide](../docs/rule-guides/proof-before-pull-request.md)). Before you open a pull request. Run the change with and without it, and quote both under "Proof in practice".
- **Session title** ([guide](../docs/rule-guides/session-title.md)). The session has a tool whose name ends in `__set_session_title`. Set `<emoji> <name>` before each turn ends.

**Memory**
- **Durable facts only** ([guide](../docs/rule-guides/memory-stores-durable-facts.md)). Writing auto-memory or a `MEMORY.md` entry. Keep only a fact that helps a fresh session weeks later.
