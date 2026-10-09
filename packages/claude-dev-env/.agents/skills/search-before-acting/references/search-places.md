# Search places

Search each place this session can reach. Start from the outcome words in the ask and from the names of the systems it touches. Try two or three phrasings, since an existing feature often uses different words than the ask, such as "workers" for "parallel" or "queue" for "batch".

| Place | What to run |
|---|---|
| Repository code | `rg -i "<outcome words>"` across each repository the work touches, and a search for the system's entry points and their flags, such as `--help` output and argument parsers |
| Open pull requests | `gh pr list --state open --search "<words>"`, or the GitHub search tool with `is:pr is:open` |
| Merged pull requests | `gh pr list --state merged --search "<words>"`, and `git log --oneline -i --grep "<words>"` on the default branch |
| Hooks | the hook registry, such as `hooks.json` or `settings.json`, and the hook directories, for a gate or reminder that already does the step |
| Rules and instructions | `rules/`, `AGENTS.md`, `CLAUDE.md`, project instructions, and memory notes |
| Skills and commands | the installed skills list, `skills/`, `.agents/skills/`, and `commands/` |
| Workflows and schedules | `.github/workflows/`, scheduled routines, cron entries, and task schedulers |
| Trackers | open and closed issues, project boards, and task cards that name the ask |
| Production config | config files, environment settings, feature flags, and launcher options that the running system reads, including values that turn on a mode the ask describes |
| Run logs and dashboards | recent run output that shows the behavior already happening |

## What to record for each hit

- The place and a link or `file:line`.
- One sentence on what it does now.
- Whether it is live: merged and running, merged and unused, or still open.

## When a place is out of reach

Name the place and the check that would reach it, such as "the production config on the build machine, read through a remote session". The report states the gap. The user may know the answer at once.
