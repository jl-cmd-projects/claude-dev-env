---
name: sync-dev-env
description: Install or update claude-dev-env in a running session, link the skills of every enabled plugin so a running session loads them, and schedule a daily re-sync at 6:00 AM local by default. Use when the user asks to sync claude-dev-env into a session, to load the skills of a plugin without a restart, to set up the daily sync, to check which session prompt a session uses, or to turn the claude-dev-env session prompt off for one session.
argument-hint: "[HH:MM] [IANA time zone]"
---

# /sync-dev-env

An always-on session starts once, so a SessionStart hook runs once and never again. Claude Code reads plugins only at session start, and a running session has no plugin reload. The skills directory is read live, so one symlink per skill makes each skill of a plugin load at once.

## 1. Install or update the package

Run `npx --yes claude-dev-env@latest --update --target ~/.claude`.

The installer leaves symlinks in the skills directory in place.

## 2. Link the plugin skills

Run `python3 "${CLAUDE_SKILL_DIR}/scripts/link_plugin_skills.py"`.

The script reads `enabledPlugins` from `~/.claude/settings.json` and the newest install of each plugin from `~/.claude/plugins/installed_plugins.json`. It links each plugin skill by its bare name. A link it owns points inside `~/.claude/plugins/cache`. On each run it re-points an owned link at the current plugin version and removes an owned link whose skill is gone or whose plugin is disabled. A name some other skill already holds is skipped and reported.

Tell the user the summary line. Report each skipped name, because a plugin skill that refers to a skipped sibling by `../<name>` reaches the other skill.

## 3. Schedule the daily sync

Skip this step when `list_triggers` already shows a routine named `Daily dev env sync` bound to this session.

The time defaults to 6:00 AM in the user's time zone. Take the time and the IANA zone from the arguments. With no zone given and none known, ask for it.

In a Claude Code cloud session, call `create_trigger`:

- `name`: `Daily dev env sync`
- `cron_expression`: `CRON_TZ=<zone> <minute> <hour> * * *`, with the minute jittered a few minutes early per the tool's guidance
- `prompt`: `/sync-dev-env`
- `initiation`: `human_request`

Bind the routine to the session whose container needs the sync. Called from that session, leave `persistent_session_id` unset. Called from another session, set `persistent_session_id` to the session that needs the sync. Never set `create_new_session_on_fire`, because a fresh session gets its own container and syncs nothing the running session reads.

Then call `list_triggers` and tell the user the routine name and its `next_run_at` in their time zone. The schedule counts as armed only once that listing shows it.

In a local Claude Code session, `CronCreate` jobs expire after 7 days. Use `/loop` or an operating system scheduler for a local daily sync.

## Session prompt

The package sets `"agent": "dev-env-session"` in `~/.claude/settings.json`. Claude Code loads that agent's body, `~/.claude/agents/dev-env-session.md`, as the system prompt of every session the settings file reaches.

When the user asks which session prompt this session uses, read the `agent` key in `~/.claude/settings.json`, then compare your loaded system prompt with the body of `~/.claude/agents/dev-env-session.md`. Report `dev-env-session` with the file path when the key is set and the body matches your loaded prompt. Report the default Claude Code prompt when the key is absent or the body differs, because a launch flag such as `--agent`, `--system-prompt` or `--settings` overrides the key.

When the user asks to turn the trimmed prompt off for one session, start that session with `claude --settings '{"agent": ""}'`. The settings file stays unchanged, so the next session loads the trimmed prompt again.

## Layout

| File | Role |
|---|---|
| `SKILL.md` | This flow: install, link, schedule |
| `scripts/link_plugin_skills.py` | Converges the skills directory on one link per enabled plugin skill |
| `scripts/test_link_plugin_skills.py` | Behavior tests for link, skip, re-point, remove, and a second run |
| `scripts/sync_dev_env_constants/config/constants.py` | Plugin file paths, settings keys, outcome names, report lines |
