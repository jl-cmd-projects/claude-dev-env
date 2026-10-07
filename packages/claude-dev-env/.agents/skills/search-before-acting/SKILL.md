---
name: search-before-acting
description: >-
  Search for what already does an ask before logging, planning, delegating,
  or building it, then report what exists in four points and wait for the
  user. Use when a user asks for new or changed behavior, a tool, a check,
  a workflow, a report, a tracker entry, or a plan, and before writing a
  brief for a worker.
---

# Search before acting

The user should hear about work that already does their ask before anyone duplicates it. Search first, report what you find, and let the user decide what to add.

## Steps

1. Restate the ask as the outcome the user wants, in their words.
2. Search every place in [`references/search-places.md`](references/search-places.md) that this session can reach. Note each place you could not reach.
3. Sort each hit as full, partial, or related. A hit is full when it already produces the outcome from step 1.
4. When any hit is full or partial, stop. Send the four-point report from [`references/report-shape.md`](references/report-shape.md) and wait for the user. When a hit is full, tell the user they already have it.
5. When nothing is found, say where you looked in one line, then continue with the playbook below.

## Playbooks

Open the playbook that matches the next move.

| Next move | Playbook |
|---|---|
| Build or change code, a hook, a skill, a rule, a workflow, or config | [`playbooks/build.md`](playbooks/build.md) |
| Log the ask in a tracker, or write a plan for it | [`playbooks/plan-or-log.md`](playbooks/plan-or-log.md) |
| Hand the ask to a worker, a thread, or another session | [`playbooks/delegate.md`](playbooks/delegate.md) |

## Layout

| File | What it holds |
|---|---|
| `SKILL.md` | The steps and the playbook index |
| `references/search-places.md` | Where to search, with the query to run in each place |
| `references/report-shape.md` | The four-point report and the "you already have it" answer |
| `playbooks/build.md` | The search and report before a build, and the pull request section |
| `playbooks/plan-or-log.md` | The search and report before a tracker entry or plan |
| `playbooks/delegate.md` | The search before a brief, and what the brief carries |
