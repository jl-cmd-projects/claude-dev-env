---
name: grok-spawn
description: >-
  Spawn headless grok worker fleets via preflight and spawn_grok_batch. Use
  when the user asks to run work on a fleet or batch of headless grok workers.
---

# Grok Spawn

Orchestrator playbook for fleets of headless grok CLI workers. This skill names
the scripts and the brief templates; it holds no spawn logic of its own.

## Gotchas

- Workers never commit, push, or call `gh`. The calling session stages, verifies,
  commits, pushes, and posts to GitHub.
- Grok has no `SendMessage` and no Claude Agent tool. Work that needs live
  teammate chat stays in this session. Each Grok worker uses `poteto-agent`.
  The runner resolves the user pstack plugin through the selected Claude
  profile's `plugins/installed_plugins.json` and includes its poteto skill content and
  its resolved path in the prompt. Each task states its role, permitted edits,
  acceptance checks, and report contract.
- Each worker gets its own `--leader-socket`. Sharing one socket across processes
  races and fails.
- Preflight is a soft gate: a fallthrough reason means skip the fleet and use
  the next tier, not a hard crash of the whole run.
- Prompt parts are plain files. Conversation-relative phrases ("as above") mean
  nothing to a headless worker — every brief stands alone.
- `spawn_grok_batch.py` re-runs preflight before launch. An early preflight call
  still helps you abort before writing the batch spec.

## When this skill applies

Use when the user asks for a **grok worker fleet**, a **headless grok batch**, or
types `/grok-spawn`.

Good fits:

- Fan-out read-only research across several paths or files
- Parallel bite-sized build work where each worker owns a closed scope

**Do not use** when the work needs:

- Live `SendMessage` coordination between agents
- Claude-only tools (Agent tool, warm advisor, Claude MCP surfaces the
  grok CLI does not load the same way)

**Refusal:** no concrete worker tasks — reply `What should the grok workers do?
List each role in one line.` and stop.

## Process

Copy this checklist and check items off as you go.

```
[ ] 1. Preflight (#96 soft gate)
[ ] 2. Write prompt-part files (briefs + report contract)
[ ] 3. Write the batch JSON spec
[ ] 4. Run spawn_grok_batch.py
[ ] 5. Read the batch summary and per-worker reports
[ ] 6. Verify, then own every git and gh step yourself
```

### 1. Preflight

Scripts ship under `$HOME/.claude/scripts/` after install (or the package
`scripts/` tree in this repo).

```bash
python "$HOME/.claude/scripts/grok_worker_preflight.py" \
  --role bugteam \
  --run-temp-dir "<run-state-dir>"
```

Optional live ping (cached under the run state dir):

```bash
python "$HOME/.claude/scripts/grok_worker_preflight.py" \
  --role bugteam \
  --ping \
  --run-temp-dir "<run-state-dir>"
```

Stdout is one line:

- `grok_preflight: ok` — continue
- `grok_preflight: fallthrough reason=<reason>` — report the reason, skip the
  fleet, fall to the next tier

Pick a fresh run state directory for the fleet (sockets, prompts, reports, ping
cache). Reuse that same path for preflight and the batch launcher.

### 2. Write prompt-part files

For each worker, write one or more part files on disk. Assemble from:

| Part | Source |
|---|---|
| Role brief | [`reference/worker-briefs.md`](reference/worker-briefs.md) — readonly or build template |
| Report contract | Same file — every worker ends with the report sections |
| Task body | Task-specific scope, paths, acceptance lines (you author this) |

Order matters: the batch launcher joins part bodies in list order after the
tool-profile header. Put the brief first, task body next, report contract last.

Flag sets and profile meaning:
[`reference/flag-profiles.md`](reference/flag-profiles.md).

### 3. Write the batch JSON spec

Write the spec from the shape and field table in
[`reference/batch-spec.md`](reference/batch-spec.md). A worker entry accepts
only the listed fields. Put the spec file under the run state directory (or any
path you pass to `--spec`).

### 4. Launch the batch

```bash
python "$HOME/.claude/scripts/spawn_grok_batch.py" \
  --spec "<batch-spec.json>" \
  --run-temp-dir "<run-state-dir>"
```

The launcher:

1. Runs preflight once for the whole batch
2. Staggers worker starts (15s between index 0, 1, 2, …)
3. Mints per-worker prompt, report, leader-socket, and debug paths
4. Prints one JSON summary on stdout

Exit code `0` only when preflight is usable and every worker is ok.

### 5. Collect reports

Read the stdout JSON:

| Key | Meaning |
|---|---|
| `is_preflight_usable` | Soft gate result |
| `preflight_reason` | Fallthrough reason, or null |
| `workers` | Per-worker reports |

Each worker entry carries `role_name`, `tool_profile`, `returncode`,
`classification`, `is_ok`, `report_text`, `output_file`, `leader_socket`,
`prompt_file`, `debug_file`.

Open each `output_file` (or use `report_text`) and check the report contract
sections. Failed workers (`is_ok` false) keep their classification
(`usage_limit`, `auth_failure`, `timeout`, `error`) for routing; read their
`debug_file` for the grok-side log of the run.

A negative `returncode` means no grok process produced it: `-1` timeout, `-2`
launch failure, `-3` the launcher itself raised before the process started (a
missing prompt-part file, for example).

### 6. Verify and own git / gh

The calling session:

1. Diffs the worktrees the build workers touched
2. Re-runs the named tests
3. Maps each acceptance line to evidence
4. Stages, commits, pushes, and posts GitHub updates as needed

Build workers stop at stage-ready edits and a written report. They do not run
`git commit`, `git push`, or `gh`.

## Composition

| Script | Role |
|---|---|
| `grok_worker_preflight.py` | Soft gate (#96): binary, auth, install, optional ping |
| `spawn_grok_batch.py` | Batch launch, stagger, report collect |
| `grok_headless_runner.py` | One-worker runner (called by the batch launcher) |

## File index

| File | Purpose |
|---|---|
| `SKILL.md` | Trigger, gotchas, process, batch shape, composition |
| `reference/worker-briefs.md` | Readonly brief, build brief, report contract templates |
| `reference/flag-profiles.md` | Readonly vs build flags, shared flags, socket and stagger rules |
| `reference/batch-spec.md` | Batch JSON spec shape and worker fields |

## Worker advisors

Each grok worker binds a unique Opus-high `advisor_session_id` through the lead-supplied `advisor.launcher` in the batch spec (the committed default is a placeholder). Reports require the same handle's ENDORSE (or bounded CORRECTION/PLAN then ENDORSE); STOP or malformed signals end as `advisor_blocked`.
