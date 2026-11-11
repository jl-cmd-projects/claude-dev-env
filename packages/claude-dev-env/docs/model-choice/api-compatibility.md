Back to [Model choice guides](README.md).

# API compatibility

## In brief

A script or app that calls the API can break when it moves to a new model. Check each item below before the switch. The source is [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/).

**When this applies:** Your own code sends Messages API requests and you change its model.

## Checklist

- **Fable 5.2 keeps its thinking.** The API returns 400 if anything before a Fable thinking block changes. You can opt in to dropping those blocks. Claude Code, the Agent SDK and Managed Agents handle this. Keep custom history append-only.
- **Opus and Fable always think.** You cannot turn thinking off. Read content blocks by their `type` field.
- **Forced tool choice fails.** `tool_choice` `any` or `tool` returns 400 on Sonnet 5.5, Opus 5.5 and Fable 5.2. Use `auto` with `strict: true`, and say in the prompt when to call the tool.
- **Computer use has one route.** Use `computer_toolset_20260801` only.
- **Haiku 4.5 to Haiku 5.5.** Replace `budget_tokens` with an effort level. Drop any non-default `temperature`, `top_p` or `top_k`. End `messages` with a user turn.
- **Safety fallbacks.** Claude Code can rerun a flagged request on an older model. Cybersecurity requests rerun on Opus 4.8, and biology requests rerun on Opus 5. The transcript notes the fallback.
- **Multi-model systems.** Build every request for the strictest model. When the routing rule is simple, let code pick the model.

Thinking blocks also move between models in a session. Read [Context and caching](context-and-caching.md).
