# subagent-models

A Claude Code mod that decides which models and agent types subagents may run as, and the effort they run at.

## What it does

- A spawn that names a turned-off model runs on the default model instead. With `offAction` set to `deny`, the spawn is refused with a message that names the model to use.
- A full model id counts by its family. `claude-fable-5-1` is fable.
- A turned-off agent type leaves the model's agent listing, and a spawn that names it is refused.
- The default model is always allowed, so a turned-off model always has somewhere to move.
- Every request a subagent makes runs at the effort you set. The main conversation keeps its own model and effort.
- With `applyToRunning` on, an effort change reaches running subagents on their next request. With it off, each subagent keeps the effort it started with until `apply`, or the bar's `apply now` button, moves them all.
- A subagent whose model comes from its agent definition is caught on its first request and moved the same way.
- A fork inherits its parent and passes untouched. So does a spawn that names no model.
- The status line shows the default model and effort, as `subagents: opus/medium`. It adds `(session)` while this session differs from the defaults.

## Settings

`/config` holds the defaults every new session starts with:

| Setting | Options | Default |
|---|---|---|
| Opus subagents | on, off | on |
| Fable subagents | on, off | off |
| Sonnet subagents | on, off | off |
| Haiku subagents | on, off | on |
| Default subagent model | opus, sonnet, haiku, fable | opus |
| Subagent effort | inherit, low, medium, high, xhigh, max | medium |
| When a spawn names a turned-off model | move, deny | move |
| Effort changes reach running subagents | on, off | on |
| Turned-off agent types | comma-separated agent types, such as `Explore, Plan` | none |

The command refuses to turn off the default model, and refuses a default model that is turned off.

## This session only

`/subagent-models` changes the current session from its next spawn, and leaves other sessions alone.

- `/subagent-models` prints the values in force and marks the ones this session changed.
- `/subagent-models fable on` sets one value for this session. Any setting name works, with one of its options.
- `/subagent-models agents` lists the agent types offered so far in this session, each with its switch.
- `/subagent-models agent Explore off` turns one agent type off for this session. `on` turns it back on.
- A framed bar above the prompt holds every setting. The top row has a chip per model (a filled dot is on, an empty dot is off), a `more` menu that saves or resets, and a `minimize` button that collapses the bar to a one-line pill. The pill's up arrow expands it again. The second row has dropdowns for the default model, effort, the turned-off action, agent types, and running subagents, plus `apply now`. A pick applies at once and a toast says what changed.
- `/subagent-models bar` minimizes the bar to its pill or expands it.
- `/subagent-models apply` moves every running subagent to the current effort now.
- `/subagent-models save` writes this session's values to the `/config` defaults.
- `/subagent-models reset` drops this session's values, so the defaults apply again.

## Install

The claude-dev-env marketplace ships the mod:

```sh
claude plugin marketplace add jl-cmd/claude-dev-env
claude plugin install subagent-models@claude-dev-env
```

Or load it from a clone for one session:

```sh
claude --plugin-dir packages/subagent-models
```

## Test

```sh
claude plugin validate .
claude plugin test .
```

Built and tested on Claude Code 2.1.288. The mod API is in early access and can change between releases.
