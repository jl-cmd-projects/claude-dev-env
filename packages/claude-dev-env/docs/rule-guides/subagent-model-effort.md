Back to the [rules index](../../rules/index.md).

# Subagent model and effort

## In brief

Every agent you start runs on an Anthropic model at an allowed effort. The allowed efforts for each model are in [`subagent_effort_levels.json`](../../hooks/hooks_constants/subagent_effort_levels.json). Name the model and the effort on every spawn.

**When this applies:** Every time one agent starts another on a Claude host. That covers the Agent and Task tools, a thread or session spawn, a Workflow agent, an advisor bind, and a headless `claude -p` run.

## Allowed pairs

[`subagent_effort_levels.json`](../../hooks/hooks_constants/subagent_effort_levels.json) is the file to edit for the allowed pairs. For each model family it lists the `allowed` efforts and the `default` effort a spawn gets when it names none or names one outside the list. The effort route hooks and the second-account worker read it on every run.

Edit the file by hand when models or their best effort levels change:

- Edit the repository copy, `packages/claude-dev-env/hooks/hooks_constants/subagent_effort_levels.json`, then reinstall. Each install writes the repository copy over the installed copy in `~/.claude/hooks/hooks_constants/`, so an edit made only there is lost at the next install.
- `ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY` in `hooks_constants/subagent_effort_route_constants.py` is the fallback copy the hooks use when the file cannot be read. Copy each edit there too. A test fails while the two differ.
- Use only the efforts `low`, `medium`, `high`, `xhigh` and `max`, keep the opus, sonnet, fable and haiku families, and put each `default` in its own `allowed` list. A file that breaks any of these, or that does not parse, writes one line to stderr that names the file and the fault, and the hooks use the built-in levels.

- Use Anthropic models only.
- Any pair the file does not allow is out.
- One exception: an advisor that is not the built-in advisor tool runs on Opus at high. The built-in advisor follows the `advisorModel` setting.

Codex spawns follow their own policy in [Automatic child model choices](../subagent-model-routing.md).

## Rule

- Name both the model and the effort. A spawn that leaves either one out takes the parent's, and the effort route hook then moves an effort outside the file to that model's default.
- A fork always takes its parent's model and effort. Fork only from a parent whose own pair the file allows.
- For `claude -p`, pass the pair as flags, such as `--model claude-opus-5-5 --effort medium` or `--model claude-sonnet-5-5 --effort high`.
- When a brief, skill, hook, setting or default gives a pair the file does not allow, use an allowed pair for that model and say so in your report.

## Which model gets which work

Pick the model by the work, then an effort the file allows for it.

- Haiku: finding files, reading logs, running tests, summing up, and sorting or pulling data out of many items. A Haiku mistake is cheap to spot.
- Sonnet: well-scoped work, such as a bug fix or a feature built to a clear spec.
- Opus: code edits, judgment calls, and decisions that rest on what other subagents report.
- Fable: the hardest work, such as a large migration, planning a design, leading many subagents, or a long run with no one watching.
- A built-in agent such as Explore runs on the session's model unless the spawn names one, so name the model.

The [model choice guides](../model-choice/README.md) cover which model, escalation, context and caching, subagents and fan-out, measuring, and API compatibility.

Source for the work split: [Which Claude model should you build with](https://claude.dev/blog/which-claude-model-should-you-build-with/).
