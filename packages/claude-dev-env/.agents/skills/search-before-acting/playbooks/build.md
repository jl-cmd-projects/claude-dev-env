# Build

Use this playbook before you build or change code, a hook, a skill, a rule, a workflow, or config for an ask.

1. Run the skill steps. Search the places in [`../references/search-places.md`](../references/search-places.md), with production config and launcher options first when the ask names a running system.
2. When a hit is full or partial, send the [report](../references/report-shape.md) and wait for the user's answer.
3. When the user says go, build only the missing part from point 3 of the report. Extend the existing piece where it lives. Start a new piece only when the existing one cannot hold the addition, and say why in the pull request.
4. When nothing exists, follow `prefer-existing-tools.md` to check open-source options, then build.
5. Add an "Existing work" section to the pull request body. List each hit with its link or `file:line` and what the pull request adds on top of it. When nothing was found, say so and name the places searched. The pull request gate denies a body without this section.

Example section:

```markdown
## Existing work

- `scripts/run_batch.py:40` already runs jobs in parallel with `--workers`. This pull request adds a per-job timeout on top of it.
- Searched open and merged pull requests for "timeout" and "workers"; none add a timeout.
```
