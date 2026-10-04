# Rules prose names only hooks that run

Full text behind [`rules/retired-hook-prose.md`](../../rules/retired-hook-prose.md), which loads in sessions as the short form.

## How a hook reaches a tool call

A hook module runs when `hooks/hooks.json` registers it or a dispatcher roster hosts it. A module can survive on disk while appearing in neither place. The installer writes an inert stand-in at a retired hook path when stale `settings.json` still names it. A missing registered path makes the interpreter exit 2, which a PreToolUse harness reads as a block.

A retired hook's logic can move into a `*_parts/` package imported by a live module. The old hook name then stops while its check still fires. A present-tense claim about the old module sends the reader to a gate they will never encounter.

The staged policy lint registers `retired-hook-prose` in `scripts/policy_lint/registry.py`. `accepts_instruction_markdown` covers Markdown under `.agents/`, `commands/`, `docs/`, `output-styles/`, `rules/`, and `system-prompts/`. The detector reads backticked hook module names, checks registration and dispatcher rosters, and reports a present-tense action attributed to a module with no live registration. The lint does not find a forced detour that names only an agent, step, or token.

A module name counts as a hook when it ends in a hook family suffix such as `_blocker`, `_enforcer`, `_gate`, `_tracker`, or `_dispatcher`, and either sits under `hooks/` or appears in `RETIRED_HOOK_REGISTRATION_RELATIVE_PATHS` in `bin/install.mjs`. A support module without a hook suffix stays outside that check.

Past-tense history makes no live claim. A sentence naming the staged policy lint, `cde_lint`, or a repository check identifies where the work runs now.

## Why gate detours matter

A gate and the standing orders written to satisfy it form one unit. A required agent spawn, token, or extra step can remain after the gate ends because those orders often omit the module name the lint searches for. The stale order costs every later session an unnecessary action.

A withdrawn threshold can also remain in an audit rubric, an agent instruction table, or a review prompt. Removing only the mechanical check leaves a judgment lane enforcing the same threshold. The archive entry records each lane so a restore can recover the complete decision.

## Sibling rules

| Rule | Role |
|---|---|
| [`archiving-agent-config.md`](../../rules/archiving-agent-config.md) | Archive a retired rule or capability with a restore record |
