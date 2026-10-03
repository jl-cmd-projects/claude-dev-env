# subagent-models

A Claude Code mod that decides which models and agent types subagents may run as, and the effort they run at.

## What it does

- A spawn that names a turned-off model runs on the default model instead. With `offAction` set to `deny`, the spawn is refused with a message that names the model to use.
- A full model id counts by its family. `claude-fable-5-1` is fable.
- A turned-off agent type leaves the model's agent listing, and a spawn that names it is refused.
- A turned-off skill still appears in the model's skill listing. When the model or you run it, the skill's text is replaced with a note that says it is off, so the model skips it. A short name such as `tdd` also matches `pstack:tdd`.
- The default model is always allowed, so a turned-off model always has somewhere to move.
- Every request a subagent makes runs at the effort you set. The main conversation keeps its own model and effort.
- With `applyToRunning` on, an effort change reaches running subagents on their next request. With it off, each subagent keeps the effort it started with until `apply`, or the bar's `apply now` button, moves them all.
- A subagent whose model comes from its agent definition is caught on its first request and moved the same way.
- A fork inherits its parent and passes untouched. So does a spawn that names no model.
- The footer pill shows the default model and effort, as `opus/medium`. A `*` marks a session that differs from the defaults. Clicking it opens or closes the bar.

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
| Turned-off skills | comma-separated skills, such as `pstack:tdd, simplify` | none |
| Days before a skill counts as unused | a whole number of days, the starting cutoff of the `unused after` menu | 14 |

The command refuses to turn off the default model, and refuses a default model that is turned off.

## This session only

`/subagent-models` changes the current session from its next spawn, and leaves other sessions alone.

- `/subagent-models` prints the values in force and marks the ones this session changed.
- `/subagent-models fable on` sets one value for this session. Any setting name works, with one of its options.
- `/subagent-models agents` lists the agent types offered so far in this session, each with its switch.
- `/subagent-models agent Explore off` turns one agent type off for this session. `on` turns it back on.
- `/subagent-models skills` lists the skills the session has, each with its switch. `/subagent-models skill pstack:tdd off` turns one skill off for this session.
- A framed bar above the prompt holds every setting in a grid of four equal columns. The header row has the title, a summary such as `opus · medium · 2 of 4 models on`, and a `minimize` button. Under it a strip of four colored segments shows which models are on, and a row of four model entries below it has a dot, the name and an `on` or `off` button each. The next row has dropdowns for the default model, effort, the turned-off action, and running subagents. The last row has the `agents` and `skills` buttons, `apply to running`, and a `more` menu that saves or resets. A pill in the footer, `◈ opus/medium ▴`, opens and closes the bar with one click.
- The `agents` and `skills` buttons open a panel with `enable all`, `disable all`, and one row per agent type or skill: a dot, the name, and an on or off button at the right edge. Every row sits in a cell as wide as the longest name, so the rows line up in columns. A name longer than 44 characters keeps its tail and loses its middle. The rows sit under a small-caps heading per namespace, such as `PSTACK` or `BRAND-VOICE`, with a count. Press a heading to fold or open its group. A group of more than 16 starts folded, and opens 40 rows at a time with a `show more` button. A list of more than 16 opens in a side pane beside the transcript, laid out in as many equal columns as the pane is wide. The button shows `▸` for a side pane and `▴` for an inline panel. A panel stays open across picks until you press its button again or close the pane. A pick applies at once and a toast says what changed.
- The mod records the time of each skill run in its own store, so the `skills` listing and panel can show when a skill was last used. The skills panel has `sort: recent`, which groups the chips as used in the last N days, unused N+ days, and never seen, newest first, with the age on each chip. The `unused after` menu picks the cutoff from 14, 28 or 56 days, starting at the `staleDays` setting, and `turn off unused Nd+ (count)` turns off the skills with a recorded date older than that cutoff. A skill with no recorded date is never turned off by that button.
- `/subagent-models bar` minimizes the bar or expands it.
- `/subagent-models seed <file>` loads last-used dates from a backfill file into the mod's own store. The store lives in the Claude config folder of the account that runs the command, so run it once in each account.
- `/subagent-models apply` moves every running subagent to the current effort now.
- `/subagent-models save` writes this session's values to the `/config` defaults.
- `/subagent-models reset` drops this session's values, so the defaults apply again.

## Backfill last-used dates

The mod only records runs from the day it loads. `scripts/backfill-last-used.mjs` reads the saved transcripts of every Claude account on the machine and writes the newest date of each skill run, for skills the model ran and slash commands you typed:

```sh
node packages/subagent-models/scripts/backfill-last-used.mjs --out dates.json
```

It scans every `~/.claude*` folder and every `~/.claude-profiles/*` folder that holds a `projects` folder, skips a folder that is a link to one it already scanned, and prints the transcript and skill-run count for each. Add `--root <config dir>` to scan only the folders you name, or `--exclude <text>` to skip a folder whose path contains the text. Then run `/subagent-models seed dates.json` in each account. Run the script's tests with `node --test packages/subagent-models/scripts/backfill-last-used.test.mjs`.

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
